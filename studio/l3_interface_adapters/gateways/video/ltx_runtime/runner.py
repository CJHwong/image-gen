"""Run one clip through the MLX q8 port, behind the studio's generic video job.

The port is a CLI with its own flags and its own habits. Everything a person does not see
lives here: the task a job maps to, the silence a short track needs, the keyframe flags, the
sampling path, and the lines its progress bar prints.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.video_job import VideoEdit, VideoJob, VideoResult
from studio.l3_interface_adapters.gateways.video.shared.engine_paths import checked_executable
from studio.l3_interface_adapters.gateways.video.shared.process_errors import crash_report as _crash_report

RUN_TIMEOUT_SECONDS = 60 * 60
# Weight loaders also print counters. Only the sampler's bar measures the render.
BAR = re.compile(r"^Denoising(?: \([^\r\n]*\))?:[^\r\n]*?\|\s*(\d+)/(\d+)\s*\[")

# A transfer can stall between progress updates. A child lets Cancel stop that read.
# Its import root must follow this runner, including when a copied tree serves the page.
LORA_FETCH = """import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from studio.l3_interface_adapters.gateways.video.shared.lora_fetch import fetch_lora
fetch_lora(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
"""


class MlxVideoRunner:
    def __init__(
        self,
        settings: dict,
        model: str,
        enhances: bool,
        keyframe_two_stage: bool = False,
        process_runner: Callable = subprocess.run,
        model_key: str = "the model",
        enhanced_prompt: Callable | None = None,
        *,
        execute_process: Callable,
    ):
        self._execute_process = execute_process
        self._enhanced_prompt = enhanced_prompt or (lambda prompt, image: False)
        self._cli = str(settings.get("cli_path", ""))
        self._ffmpeg = str(settings.get("ffmpeg_path") or (shutil.which("ffmpeg") or ""))
        self._model = model
        self._batch_policy = settings.get("batch_policy", "auto")
        if self._batch_policy not in ("auto", "enhance_only", "sequential"):
            raise StudioError("Set batch_policy under [mlx_video] to auto, enhance_only or sequential.")
        self._model_key = model_key
        self._lora_dir = str(settings.get("lora_dir") or "")
        # Fetching a missing adapter is a download the person did not ask for, so the
        # setting decides. Off by default, and the file is named either way.
        self._fetches_loras = bool(settings.get("fetch_loras", False))
        # The CLI's separate Gemma 3 enhancement pass runs before either video pack.
        # LTX-2.5 still uses its pack-local Gemma 4 tower for prompt encoding afterwards.
        self._enhances = enhances
        # On 2.3 the distilled path holds the room until the last keyframe and lands the
        # change in one frame. The two-stage path builds it through the clip, so a keyframe
        # job takes it there. The 2.5 distilled path already builds it.
        self._keyframe_two_stage = keyframe_two_stage
        self._process_runner = process_runner

    def _prepared_job(self, job):
        if job.enhance and self._enhanced_prompt(job.prompt, job.references):
            return replace(job, enhance=False)
        return job

    def run(
        self,
        job: VideoJob,
        progress: Callable[[int, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> VideoResult:
        job = self._prepared_job(job)
        if not self._model:
            raise StudioError(f"Set {self._model_key} under [mlx_video] to a q8 pack id.")
        self._checked(self._cli, "Set cli_path under [mlx_video] to the MLX port's executable.")
        with tempfile.TemporaryDirectory(prefix="studio-mlx-") as scratch:
            root = Path(scratch)
            output = root / "output.mp4"
            if job.edit is not None:
                command = self._edit_command(job, job.edit, root, output, cancelled)
            else:
                images = self._write_references(job, root)
                audio = self._write_audio(job, root)
                command = self._command(job, output, images, audio)
                if (audio is not None or images) and job.enhance and self._enhances:
                    python = self._checked(
                        str(Path(self._cli).parent / "python"), "The MLX CLI needs its environment's python."
                    )
                    child = Path(__file__).with_name("mlx_video_generation_child.py")
                    command = [python, str(child), *command[1:]]
            self._execute(command, progress, cancelled, fast_mode=job.fast_mode)
            if not output.is_file() or output.stat().st_size == 0:
                raise StudioError("The MLX video pipeline did not write an MP4 file.")
            mp4 = output.read_bytes()
        return VideoResult(mp4, job.width, job.height, job.num_frames, job.frame_rate, job.seed)

    def run_batch(self, jobs, completed, started, progress, cancelled) -> list[VideoResult]:
        from studio.l3_interface_adapters.gateways.video.ltx_runtime.batch import (
            BatchRecords,
            prefer_sequential,
            reuse_policy,
        )

        jobs = [self._prepared_job(job) for job in jobs]
        if cancelled():
            raise Cancelled("The video batch was cancelled.")
        if len({job.fast_mode for job in jobs}) > 1:
            return self._sequential_batch(jobs, completed, started, progress, cancelled)
        if self._batch_policy == "auto" and self._enhances and prefer_sequential(jobs, self._model):
            return self._sequential_batch(jobs, completed, started, progress, cancelled)
        python = Path(self._cli).parent / "python"
        enhancing = (
            self._batch_policy != "sequential"
            and self._enhances
            and len(jobs) > 1
            and all(job.edit is None for job in jobs)
            and any(job.enhance for job in jobs)
        )
        policy = reuse_policy(jobs, self._model) if self._batch_policy == "auto" else None
        if (policy is None and not enhancing) or not python.is_file():
            return self._sequential_batch(jobs, completed, started, progress, cancelled)
        if not self._model:
            raise StudioError(f"Set {self._model_key} under [mlx_video] to a q8 pack id.")
        self._checked(self._cli, "Set cli_path under [mlx_video] to the MLX port's executable.")
        with tempfile.TemporaryDirectory(prefix="studio-mlx-batch-") as scratch:
            root = Path(scratch)
            commands = []
            for index, job in enumerate(jobs, 1):
                if cancelled():
                    raise Cancelled("The video batch was cancelled.")
                item = root / str(index)
                item.mkdir()
                images = self._write_references(job, item)
                audio = self._write_audio(job, item)
                command = self._command(job, root / f"{index}.mp4", images, audio)
                if audio is not None and job.enhance and self._enhances:
                    # The enhancement child consumes this marker before the a2v parser sees it.
                    command.append("--enhance-prompt")
                commands.append(command)
            manifest = root / "commands.json"
            manifest.write_text(json.dumps(commands))
            if enhancing:
                child = Path(__file__).with_name("mlx_video_batch_enhancement.py")
                self._execute([str(python), str(child), str(manifest)], None, cancelled)
                commands = json.loads(manifest.read_text())
            records = BatchRecords(jobs, commands, root, completed, started, progress, cancelled)
            child = Path(__file__).with_name("mlx_video_batch_child.py")
            self._execute(
                [str(python), str(child), policy or "sequential", str(manifest)],
                None,
                cancelled,
                records.feed,
                lambda: records.item_started_at,
                fast_mode=jobs[0].fast_mode,
            )
            if len(records.results) != len(jobs):
                raise StudioError("The MLX video batch ended before every item finished.")
            return records.results

    def _sequential_batch(self, jobs, completed, started, progress, cancelled) -> list[VideoResult]:
        results = []
        for index, job in enumerate(jobs, 1):
            if cancelled():
                raise Cancelled("The video batch was cancelled.")
            started(index, len(jobs))
            result = self.run(job, progress, cancelled)
            completed(index, result)
            results.append(result)
        return results

    def _command(
        self,
        job: VideoJob,
        output: Path,
        images: list[Path],
        audio: Path | None,
    ) -> list[str]:
        # A track turns the job into the audio-to-video task; every other job draws a clip,
        # and the distilled path is the fast one for both packs.
        command = [
            self._cli,
            "a2v" if audio is not None else "generate",
            "-p",
            job.prompt,
            "-H",
            str(job.height),
            "-W",
            str(job.width),
            "-f",
            str(job.num_frames),
            "--frame-rate",
            str(job.frame_rate),
            "--model",
            self._model,
            "-o",
            str(output),
        ]
        if audio is not None:
            command.extend(("--audio", str(audio)))
        elif images and self._keyframe_two_stage:
            command.append("--two-stage")
        else:
            command.append("--distilled")
        # Pin the existing schedules so the progress total describes this invocation,
        # even if a later engine release changes its defaults.
        stage1 = 8 if "--distilled" in command else 30
        command.extend(("--stage1-steps", str(stage1), "--stage2-steps", "3"))
        if job.seed is not None:
            command.extend(("--seed", str(job.seed)))
        if audio is None and job.enhance and self._enhances:
            command.append("--enhance-prompt")
        for path, reference in zip(images, job.references, strict=True):
            command.extend(("--image", str(path), str(reference.frame_index), f"{reference.strength:g}"))
        return command

    def _edit_command(
        self,
        job: VideoJob,
        edit: VideoEdit,
        root: Path,
        output: Path,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[str]:
        """An effect run, on the single-stage path.

        The port's default IC-LoRA path is two-stage and applies the reference at half
        resolution, which turns a 2.5 effect into a tiled artifact. The single-stage path
        applies the reference at full resolution throughout, and the 2.5 weights answer to it.
        """
        clip = root / "conditioning.mp4"
        clip.write_bytes(edit.clip)
        lora = self._lora(edit, cancelled)
        command = [
            self._cli,
            "ic-lora",
            "-p",
            job.prompt,
            "--lora",
            str(lora),
            f"{edit.strength:g}",
            "--video-conditioning",
            str(clip),
            "1.0",
            "-H",
            str(job.height),
            "-W",
            str(job.width),
            "-f",
            str(job.num_frames),
            "--frame-rate",
            str(job.frame_rate),
            "--model",
            self._model,
            "--single-stage",
            "--stage1-steps",
            "8",
            "--stage2-steps",
            "0",
            "-o",
            str(output),
        ]
        if job.seed is not None:
            command.extend(("--seed", str(job.seed)))
        return command

    def _lora(self, edit: VideoEdit, cancelled: Callable[[], bool] | None = None) -> Path:
        """The adapter's weights, on disk.

        A file that is missing is fetched from Lightricks when the setting allows it, and
        refused with the path when it does not. The fetch is a download, so it is the
        setting's decision and not the runner's.
        """
        if not self._lora_dir:
            raise StudioError("Set lora_dir under [mlx_video] to the adapter directory.")
        path = Path(self._lora_dir) / edit.lora_file
        if path.is_file():
            return path
        if not self._fetches_loras:
            raise StudioError(
                f"The adapter's weights are not on disk at {path}. Fetch the file from the "
                f"Lightricks collection at https://huggingface.co/Lightricks into {self._lora_dir}, "
                f"or set fetch_loras to true under [mlx_video] and the studio will fetch it."
            )
        self._execute(
            [
                sys.executable,
                "-c",
                LORA_FETCH,
                str(Path(__file__).resolve().parents[5]),
                edit.adapter,
                edit.lora_file,
                str(path.parent.absolute()),
            ],
            None,
            cancelled,
        )
        return path

    def _write_references(self, job: VideoJob, root: Path) -> list[Path]:
        paths = []
        for index, reference in enumerate(job.references):
            path = root / f"reference-{index}.png"
            path.write_bytes(reference.png)
            paths.append(path)
        return paths

    def _write_audio(self, job: VideoJob, root: Path) -> Path | None:
        """The track, padded to the clip's length.

        The port refuses a track shorter than the clip instead of trimming or looping it, so
        the runner gives it the length the form asked for and lets silence follow the speech.
        """
        if job.audio is None:
            return None
        ffmpeg = self._checked(self._ffmpeg, "Set ffmpeg_path under [mlx_video] to ffmpeg.")
        suffix = Path(job.audio.name).suffix or ".bin"
        # The source keeps its own name so ffmpeg never reads and writes one file.
        source = root / f"source{suffix}"
        source.write_bytes(job.audio.data)
        target = root / "padded.wav"
        seconds = job.num_frames / job.frame_rate + 0.1
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-af",
            "apad",
            "-t",
            f"{seconds:.3f}",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(target),
        ]
        result = self._process_runner(command, capture_output=True)
        if result.returncode:
            detail = result.stderr.decode(errors="replace").strip().splitlines()[-1:] or [""]
            raise StudioError(f"The track could not be padded to the clip: {detail[0]}")
        return target

    _checked = staticmethod(checked_executable)

    def _execute(
        self,
        command: list[str],
        progress: Callable[[int, int, int], None] | None,
        cancelled: Callable[[], bool] | None = None,
        consume: Callable[[str], None] | None = None,
        timeout_started: Callable[[], float | None] | None = None,
        *,
        fast_mode: bool | None = None,
    ) -> None:
        reporter = _RenderProgress(command, progress) if progress else None

        def feed(text):
            if consume:
                consume(text)
            if reporter:
                reporter.feed(text)

        environment = {}
        if fast_mode is not None:
            environment["LTX2_COMPUTE_DTYPE"] = "float16" if fast_mode else "float32"
        self._execute_process(
            command,
            cancelled,
            feed,
            timeout_started,
            environment=environment,
            timeout_seconds=RUN_TIMEOUT_SECONDS,
            timeout_message="The MLX video pipeline timed out after one hour.",
            cancel_message="video generation was cancelled",
            failure_message=_crash_report,
        )


class _RenderProgress:
    """Join sampler counters across stages and pipe reads."""

    def __init__(self, command: list[str], publish: Callable[[int, int, int], None]):
        self._total = sum(int(command[command.index(flag) + 1]) for flag in ("--stage1-steps", "--stage2-steps"))
        self._publish = publish
        self._pending = ""
        self._last = (0, 0)
        self._offset = 0
        self._phase = 1
        self._reported = -1

    def feed(self, text: str) -> None:
        records = re.split(r"[\r\n]", self._pending + text)
        self._pending = records[-1][-4096:]
        for record in records:
            # The engine can close its bar at n-1. Decoder loading is the first
            # reliable signal that every sampler has finished.
            if record.startswith(("[Loading decoders (", "[Decoding video ")):
                self._report(self._total)
            match = BAR.search(record)
            if match:
                self._counter(int(match.group(1)), int(match.group(2)))

    def _counter(self, step: int, total: int) -> None:
        previous, previous_total = self._last
        if previous_total and (total != previous_total or step < previous):
            self._offset += previous_total
            self._phase += 1
        self._last = (step, total)
        self._report(min(self._offset + step, self._total))

    def _report(self, completed: int) -> None:
        if completed > self._reported:
            self._publish(completed, self._total, self._phase)
            self._reported = completed
