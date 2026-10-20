"""Run one clip through the MLX q8 port, behind the studio's generic video job.

The port is a CLI with its own flags and its own habits. Everything a person does not see
lives here: the task a job maps to, the silence a short track needs, the keyframe flags, the
sampling path, and the lines its progress bar prints.
"""

import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, cast

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.video_job import VideoEdit, VideoJob, VideoResult
from studio.l3_interface_adapters.gateways.mlx_video.lora_fetch import fetch_lora

RUN_TIMEOUT_SECONDS = 60 * 60
TAIL_LINES = 12
# The port's bar reads `Denoising:  25%|##  | 2/8 [00:04<...]`, and it writes carriage
# returns between updates, so the reader looks for the counter rather than for a line.
BAR = re.compile(r"(\d+)/(\d+)\s*\[")


class MlxVideoRunner:
    def __init__(
        self,
        settings: dict,
        model: str,
        enhances: bool,
        keyframe_two_stage: bool = False,
        process_runner: Callable = subprocess.run,
        model_key: str = "the model",
    ):
        self._cli = str(settings.get("cli_path", ""))
        self._ffmpeg = str(settings.get("ffmpeg_path") or (shutil.which("ffmpeg") or ""))
        self._model = model
        self._model_key = model_key
        self._lora_dir = str(settings.get("lora_dir") or "")
        # Fetching a missing adapter is a download the person did not ask for, so the
        # setting decides. Off by default, and the file is named either way.
        self._fetches_loras = bool(settings.get("fetch_loras", False))
        # The enhancer is a Gemma 3 pass, which the 2.5 pack cannot run. The job always
        # carries the flag, so the runner drops it here and the form sends one shape.
        self._enhances = enhances
        # On 2.3 the distilled path holds the room until the last keyframe and lands the
        # change in one frame. The two-stage path builds it through the clip, so a keyframe
        # job takes it there. The 2.5 distilled path already builds it.
        self._keyframe_two_stage = keyframe_two_stage
        self._process_runner = process_runner

    def run(
        self,
        job: VideoJob,
        progress: Callable[[int, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> VideoResult:
        if not self._model:
            raise StudioError(f"Set {self._model_key} under [mlx_video] to a q8 pack id.")
        self._checked(self._cli, "Set cli_path under [mlx_video] to the MLX port's executable.")
        with tempfile.TemporaryDirectory(prefix="studio-mlx-") as scratch:
            root = Path(scratch)
            output = root / "output.mp4"
            if job.edit is not None:
                command = self._edit_command(job, job.edit, root, output)
            else:
                images = self._write_references(job, root)
                audio = self._write_audio(job, root)
                command = self._command(job, output, images, audio)
            self._execute(command, progress, cancelled)
            if not output.is_file() or output.stat().st_size == 0:
                raise StudioError("The MLX video pipeline did not write an MP4 file.")
            mp4 = output.read_bytes()
        return VideoResult(mp4, job.width, job.height, job.num_frames, job.frame_rate, job.seed)

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
        if job.seed is not None:
            command.extend(("--seed", str(job.seed)))
        if job.enhance and self._enhances:
            command.append("--enhance-prompt")
        for path, reference in zip(images, job.references, strict=True):
            command.extend(("--image", str(path), str(reference.frame_index), f"{reference.strength:g}"))
        return command

    def _edit_command(self, job: VideoJob, edit: VideoEdit, root: Path, output: Path) -> list[str]:
        """An effect run, on the single-stage path.

        The port's default IC-LoRA path is two-stage and applies the reference at half
        resolution, which turns a 2.5 effect into a tiled artifact. The single-stage path
        applies the reference at full resolution throughout, and the 2.5 weights answer to it.
        """
        clip = root / "conditioning.mp4"
        clip.write_bytes(edit.clip)
        lora = self._lora(edit)
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
            "-o",
            str(output),
        ]
        if job.seed is not None:
            command.extend(("--seed", str(job.seed)))
        return command

    def _lora(self, edit: VideoEdit) -> Path:
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
        return fetch_lora(edit.adapter, edit.lora_file, Path(self._lora_dir))

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

    def _checked(self, value: str, message: str) -> str:
        if not value:
            raise StudioError(message)
        path = Path(value).expanduser()
        if path.is_file():
            return str(path.absolute())
        found = shutil.which(value)
        if found:
            return found
        raise StudioError(message)

    def _execute(
        self,
        command: list[str],
        progress: Callable[[int, int, int], None] | None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        should_cancel = cancelled or (lambda: False)
        with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, bufsize=0) as process:
            stderr = cast(BinaryIO, process.stderr)
            started = time.monotonic()
            recent: deque[str] = deque(maxlen=TAIL_LINES)
            reported = (0, 0)
            with selectors.DefaultSelector() as selector:
                selector.register(stderr, selectors.EVENT_READ)
                while selector.get_map():
                    if should_cancel():
                        _stop_process(process)
                        raise Cancelled("video generation was cancelled")
                    remaining = RUN_TIMEOUT_SECONDS - (time.monotonic() - started)
                    if remaining <= 0:
                        process.kill()
                        process.wait()
                        raise StudioError("The MLX video pipeline timed out after one hour.")
                    if not selector.select(min(0.25, remaining)):
                        continue
                    chunk = os.read(stderr.fileno(), 4096)
                    if not chunk:
                        selector.unregister(stderr)
                        continue
                    text = chunk.decode(errors="replace")
                    recent.extend(line for line in re.split(r"[\r\n]+", text) if line.strip())
                    if progress:
                        reported = _report(text, reported, progress)
            return_code = process.wait(timeout=max(0.01, RUN_TIMEOUT_SECONDS - (time.monotonic() - started)))
            if should_cancel():
                raise Cancelled("video generation was cancelled")
            if return_code:
                raise StudioError(_crash_report(return_code, recent))


def _report(text: str, reported: tuple[int, int], progress: Callable[[int, int, int], None]) -> tuple[int, int]:
    """Publish the last counter in a chunk, once per new value."""
    for match in BAR.finditer(text):
        step, total = int(match.group(1)), int(match.group(2))
        if (step, total) != reported:
            progress(step, total, 1)
            reported = (step, total)
    return reported


# What a failed weight fetch looks like, and the step it needs. The first run downloads
# about 72 GB, so the common failure is an unprepared machine, not a broken render. The
# tail stays after the hint: the class name and the status are what a report needs.
FETCH_FIXES = (
    (
        ("gatedrepoerror", "cannot access gated repo"),
        "The weights sit in a gated repo. Accept its terms on the model page and run "
        "`uv run hf auth login` once, then run this again.",
    ),
    (
        ("repositorynotfounderror", "repository not found"),
        "No Hugging Face repo has that id. Check the pack id under [mlx_video] in studio.toml.",
    ),
    (
        ("connectionerror", "maxretryerror", "nameresolutionerror"),
        "The studio could not reach Hugging Face. Check the network, then run this again.",
    ),
)


def _crash_report(return_code: int, recent: deque[str]) -> str:
    tail = " | ".join(list(recent)[-TAIL_LINES:])
    if not tail:
        return f"MLX video pipeline failed with exit status {return_code} and said nothing."
    hint = _fetch_fix(tail)
    lead = f"{hint} " if hint else ""
    return f"{lead}MLX video pipeline failed with exit status {return_code}. Its last lines: {tail}"


def _fetch_fix(tail: str) -> str:
    lowered = tail.lower()
    for needles, fix in FETCH_FIXES:
        if any(needle in lowered for needle in needles):
            return fix
    return ""


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
