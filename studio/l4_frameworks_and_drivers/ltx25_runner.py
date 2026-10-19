"""Run the official LTX-2.5 distilled pipeline and fetch its weights on first use."""

import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from collections import deque
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import BinaryIO, cast

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.video_job import VideoJob, VideoResult

MODEL_PATHS = {
    "transformer": "diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors",
    "text_encoder": "text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
    "video_vae": "vae/ltx-2.5-video-vae-bf16.safetensors",
    "audio_vae": "vae/ltx-2.5-audio-vae-bf16.safetensors",
    "duration_head": "model_patches/ltx-2.5-duration-head-bf16.safetensors",
    "spatial_upsampler": "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
}
MODEL_FILES = tuple(MODEL_PATHS.values())
# The audio pipeline runs the full model in its first stage and refines with a distilled
# LoRA, so it needs two files the drawing pipeline never opens. They are fetched only for a
# run that follows a track, because the pair is 50.9 GB and a studio that draws clips has no
# use for either. Measured off the Hugging Face file list on 2026-10-19: the transformer is
# 42.0 GB and the LoRA 8.9 GB.
AUDIO_MODEL_PATHS = {
    "audio_transformer": "diffusion_models/ltx-2.5-22b-dev-transformer-bf16.safetensors",
    "distilled_lora": "loras/ltx-2.5-22b-distilled-lora-450-bf16.safetensors",
}
AUDIO_MODEL_FILES = tuple(AUDIO_MODEL_PATHS.values())
# The guided first stage's step count. The engine resolves the same number from the
# checkpoint's own version metadata (LTX 2.4 and later run 30), and it is passed rather than
# inherited so the progress bar's total is a fact this runner knows instead of a guess.
AUDIO_STEPS = 30
# The LoRA's own strength: the card ships it at full weight for the refinement pass.
DISTILLED_LORA_STRENGTH = 1.0
# A track is decoded before the render, so a file the engine cannot read fails in a second
# rather than inside the audio VAE after the transformer has loaded.
AUDIO_DECODE_TIMEOUT_SECONDS = 120
MODEL_REPOSITORY = "Lightricks/LTX-2.5"
# How many of the pipeline's last lines a crash keeps.
STDERR_TAIL_LINES = 12
RUN_TIMEOUT_SECONDS = 3600
# How hard the clip steers an edit. The cards' own loader uses the reference at full strength,
# and the adapter's own weight rides in --lora instead, which is the knob the form offers.
CONDITIONING_STRENGTH = 1.0
PROGRESS_WRAPPER = """import contextlib
import importlib
import sys

import ltx_pipelines.utils.blocks as blocks
import ltx_pipelines.utils.samplers as samplers
from ltx_pipelines.utils.constants import DISTILLED_SIGMA_VALUES, STAGE_2_DISTILLED_SIGMA_VALUES

# Which pipeline this run is. The runner passes its module name first, because the ones it
# can drive are entered the same way and the wrapper has to hook whichever one runs.
pipeline_name = sys.argv.pop(1)
pipeline = importlib.import_module(pipeline_name)

# The distilled pipeline denoises the clip twice: once at its own resolution, then
# again after the spatial upsampler. The pipeline runs one window for the studio,
# so each of those two stages samples exactly once, and a stage's step count is
# the schedule it samples with. The page shows one percentage for the whole
# render, so the two stages have to arrive as one count, and the count has to be
# known before the first step: the schedules are read from the pipeline rather
# than guessed, and one window is what the runner's own flags ask for.
#
# A step is reported as it starts, not as it ends. The sampler breaks out of its
# loop on the terminal sigma instead of running the iterator dry, so the loop is
# gone before the generator would resume after its last yield. A report written
# after the yield never fires for a stage's last step, which left the bar parked
# at 10 of 11 and a render that never reached the end of its own count. Measured
# on the office machine: two calls, the pipeline logging 8 then 3 steps, and 7
# then 2 resumes, which is one short each.
stage_steps = (len(DISTILLED_SIGMA_VALUES) - 1, len(STAGE_2_DISTILLED_SIGMA_VALUES) - 1)
if pipeline_name == "ltx_pipelines.a2vid_two_stage":
    # The audio pipeline's first stage is the guided schedule, not the distilled one: it
    # samples the step count the runner asked for, and its second stage refines with the
    # distilled schedule. The count is read off the same argv the pipeline itself parses.
    stage_steps = (
        int(sys.argv[sys.argv.index("--num-inference-steps") + 1]),
        len(STAGE_2_DISTILLED_SIGMA_VALUES) - 1,
    )
total_steps = sum(stage_steps)
state = {"stage": 0}

def report_steps(iterable, *args, **kwargs):
    stage = state["stage"]
    state["stage"] = stage + 1
    done_before = sum(stage_steps[:stage])
    for step, value in enumerate(iterable, 1):
        print(f"STUDIO_STEP 1 {done_before + step} {total_steps}", file=sys.stderr, flush=True)
        yield value

samplers.tqdm = report_steps

# A stage builds its transformer for each denoise pass and frees it when the pass
# returns, so one clip reads the 39.1 GB file twice. The second read is waste: the
# build does not depend on the shape of the latents, because the single GPU builder
# ignores the video tools the stage hands it. Measured on the office M5 Pro, one
# 384 x 384 clip of 73 frames, the second build cost 32.4 s and 36.2 s in two runs,
# and holding the first build instead made the same clip: 73 frames of 73 identical
# and no audio difference.
#
# The video encoder is the other block a clip builds twice, once for a reference frame
# and once inside the upsampler. It is 0.59 GB and about a second of the upsampler's
# 2.4 s, and it is not held. Sharing it means copying those two blocks' own call bodies,
# which would drift from the pipeline and could skip the upsample step itself, or
# caching inside the loader that builds it, which risks handing back the wrong model.
# Neither is worth 0.7 percent of a clip.
#
# The hold ends when the second pass does. The pipeline runs one denoise pass per
# stage, and its two stages are the two calls in stream_chunks, so the second pass is
# the last one and the decode that wants the room comes after it. A run that reached
# only one pass would hold its transformer until the process exits, which is the
# memory this gives back and not correctness.
#
# One slot, because a clip has one stage: a pipeline that built a stage per pass would
# otherwise hold a transformer per pass, and two of those do not fit on this machine.
held = {"stage": None, "context": None, "model": None}

def hold_transformer():
    original = blocks.DiffusionStage._transformer_ctx

    def holding(self, **kwargs):
        # The block streaming path frees its blocks between passes by design.
        if self._is_streaming:
            return original(self, **kwargs)

        @contextlib.contextmanager
        def reuse():
            if held["stage"] is not self:
                release_held()
                held["context"] = original(self, **kwargs)
                held["model"] = held["context"].__enter__()
                held["stage"] = self
            yield held["model"]

        return reuse()

    blocks.DiffusionStage._transformer_ctx = holding

def release_held():
    if held["context"] is not None:
        held["context"].__exit__(None, None, None)
    held["stage"] = None
    held["context"] = None
    held["model"] = None

def release_after_last_pass():
    original = pipeline.denoise_chunks
    seen = {"passes": 0}

    def counting(*args, **kwargs):
        seen["passes"] += 1
        this_pass = seen["passes"]

        def exhaust():
            try:
                yield from original(*args, **kwargs)
            finally:
                if this_pass >= 2:
                    release_held()

        return exhaust()

    pipeline.denoise_chunks = counting

hold_transformer()
release_after_last_pass()
pipeline.main()
"""
PROGRESS_RECORD = re.compile(r"STUDIO_STEP (\d+) (\d+) (\d+)")
DOWNLOAD_SCRIPT = """import json
import sys
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id=sys.argv[1],
    allow_patterns=json.loads(sys.argv[2]),
    local_dir=sys.argv[3],
)
"""
# The audio VAE's first convolution takes two channels, and nothing between the decoder and
# that convolution upmixes a mono track: measured on 2026-10-19, a mono WAV died there with
# `expected input[1, 1, 107, 66] to have 2 channels`. The engine's own environment decodes
# every container it reads, so it is asked to write the stereo PCM the model wants. Only the
# clip's own seconds are written: the pipeline clips the track to the frame count anyway,
# and a long track would otherwise leave a gigabyte of PCM in the scratch directory.
AUDIO_DECODE_SCRIPT = """import sys

import av

source, target, seconds = sys.argv[1], sys.argv[2], float(sys.argv[3])
with av.open(source) as container:
    stream = next(one for one in container.streams if one.type == "audio")
    limit = int(stream.rate * seconds)
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="stereo", rate=stream.rate)
    written = 0
    with av.open(target, "w") as output:
        out_stream = output.add_stream("pcm_s16le", rate=stream.rate, layout="stereo")
        for frame in container.decode(stream):
            if written >= limit:
                break
            for converted in resampler.resample(frame) or ():
                if converted is None:
                    continue
                if written + converted.samples > limit:
                    break
                for packet in out_stream.encode(converted):
                    output.mux(packet)
                written += converted.samples
        for packet in out_stream.encode(None):
            output.mux(packet)
"""


class Ltx25Runner:
    def __init__(
        self,
        python_path: str,
        model_dir: str | Path,
        process_runner: Callable = subprocess.run,
        model_downloader: Callable[[Path], None] | None = None,
        prompt_enhancer_root: str | Path | None = None,
        lora_dir: str | Path | None = None,
    ):
        self._python_path = python_path
        # The video model's own prompt enhancer is a second Gemma, fetched from its own
        # repository and not by this runner's weight download, which knows one model only.
        self._prompt_enhancer_root = Path(str(prompt_enhancer_root)).expanduser() if prompt_enhancer_root else None
        # The IC-LoRA adapters come from their own repositories too, one file each, and an
        # edit names one by file: the directory is configured and the file is the adapter's.
        self._lora_dir = Path(str(lora_dir)).expanduser() if lora_dir else None
        self._model_dir_value = str(model_dir).strip() if model_dir is not None else ""
        self._model_dir = Path(self._model_dir_value).expanduser()
        self._process_runner = process_runner
        self._model_downloader = model_downloader

    def run(
        self,
        job: VideoJob,
        progress: Callable[[int, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> VideoResult:
        python = self._python()
        model_paths = self._model_paths(python, cancelled, audio=job.audio is not None)
        with tempfile.TemporaryDirectory(prefix="studio-ltx25-") as scratch:
            output_path = Path(scratch) / "output.mp4"
            image_arguments = self._write_references(job, Path(scratch))
            audio_path = self._write_audio(python, job, Path(scratch))
            command = self._command(
                python,
                model_paths,
                job,
                output_path,
                image_arguments,
                self._enhancer_for(job),
                self._edit_arguments(job, Path(scratch)),
                audio_path,
            )
            if progress:
                # The hold on the transformer rides with this wrapper, so a run that asks
                # for no progress reports runs the pipeline directly and holds nothing.
                # The studio always asks, so every run it makes takes the wrapper.
                script_path = Path(scratch) / "ltx25_progress.py"
                script_path.write_text(PROGRESS_WRAPPER, encoding="utf-8")
                # The wrapper is handed the pipeline's module name first, the way `-m` takes it,
                # so one script can drive either pipeline and hook whichever one runs.
                command = [python, str(script_path), *command[2:]]
            self._execute(command, progress, cancelled)
            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise StudioError("The LTX-2.5 pipeline did not write an MP4 file.")
            mp4 = output_path.read_bytes()
        return VideoResult(mp4, job.width, job.height, job.num_frames, job.frame_rate, job.seed)

    def _python(self) -> str:
        if not self._python_path:
            raise StudioError("Set python_path under [ltx25] to the LTX-2.5 Python environment.")
        configured_path = Path(self._python_path).expanduser()
        if configured_path.is_file():
            # Keep venv symlinks intact; resolving one bypasses its site-packages.
            return str(configured_path.absolute())
        command_path = shutil.which(self._python_path)
        if command_path:
            return command_path
        raise StudioError(f"The configured LTX-2.5 Python executable is missing: {self._python_path}")

    def _model_paths(self, python: str, cancelled: Callable[[], bool] | None, audio: bool = False) -> dict[str, Path]:
        if not self._model_dir_value or self._model_dir.resolve() == Path.cwd().resolve():
            raise StudioError("Set a dedicated model_dir under [ltx25] before video generation.")
        # A run that follows a track opens two files more, and they are half a hundred
        # gigabytes: they are required, and fetched, only for that run.
        wanted = MODEL_FILES + (AUDIO_MODEL_FILES if audio else ())
        missing = [relative for relative in wanted if not (self._model_dir / relative).is_file()]
        if missing:
            if self._model_downloader:
                self._model_downloader(self._model_dir)
            else:
                self._download_model(python, self._model_dir, cancelled, wanted)
        missing = [relative for relative in wanted if not (self._model_dir / relative).is_file()]
        if missing:
            raise StudioError(f"The LTX-2.5 local weights are incomplete: {', '.join(missing)}")
        paths = {name: self._model_dir / relative for name, relative in MODEL_PATHS.items()}
        if audio:
            paths.update({name: self._model_dir / relative for name, relative in AUDIO_MODEL_PATHS.items()})
        return paths

    @staticmethod
    def _download_model(
        python: str,
        model_dir: Path,
        cancelled: Callable[[], bool] | None,
        files: tuple[str, ...] = MODEL_FILES,
    ) -> None:
        command = [python, "-c", DOWNLOAD_SCRIPT, MODEL_REPOSITORY, json.dumps(list(files)), str(model_dir)]
        try:
            model_dir.mkdir(parents=True, exist_ok=True)
            Ltx25Runner._execute_with_progress(command, None, cancelled)
        except Cancelled:
            raise
        except FileNotFoundError:
            raise StudioError("The configured LTX-2.5 Python executable could not start.") from None
        except subprocess.CalledProcessError as error:
            raise StudioError(
                f"LTX-2.5 weights download failed (exit status {error.returncode}). "
                "Run `hf auth login`, accept access at "
                "https://huggingface.co/Lightricks/LTX-2.5, and check the network."
            ) from None
        except subprocess.TimeoutExpired:
            raise StudioError("LTX-2.5 weights download timed out after one hour.") from None

    def _enhancer_for(self, job: VideoJob) -> Path | None:
        """The prompt enhancer's directory, or a refusal that says how to get it.

        The enhancer's weights come from their own repository and this runner does not fetch
        them, so a run that asks for the enhancer with nothing on disk would otherwise die
        inside the pipeline over a path nobody can act on.
        """
        if not job.enhance:
            return None
        if self._prompt_enhancer_root is None or not self._prompt_enhancer_root.is_dir():
            raise StudioError(
                "This run asked for the video model's own prompt enhancer and its weights are "
                f"not on disk at {self._prompt_enhancer_root}. Download them with `hf download "
                "google/gemma-4-E2B-it --local-dir <dir>`, then point prompt_enhancer_gemma_root "
                "in the ltx25 section of studio.toml at that directory."
            )
        return self._prompt_enhancer_root

    @staticmethod
    def _write_references(job: VideoJob, scratch: Path) -> list[tuple[Path, int, float]]:
        arguments = []
        for index, reference in enumerate(job.references):
            image_path = scratch / f"reference-{index}.png"
            image_path.write_bytes(reference.png)
            arguments.append((image_path, reference.frame_index, reference.strength))
        return arguments

    def _write_audio(self, python: str, job: VideoJob, scratch: Path) -> Path | None:
        """The track on disk, decoded to the stereo PCM the audio VAE takes."""
        if job.audio is None:
            return None
        source = scratch / "audio-source"
        source.write_bytes(job.audio.data)
        target = scratch / "audio.wav"
        self._normalize_audio(python, source, target, job.num_frames / job.frame_rate)
        return target

    @staticmethod
    def _normalize_audio(python: str, source: Path, target: Path, seconds: float) -> None:
        try:
            subprocess.run(
                [python, "-c", AUDIO_DECODE_SCRIPT, str(source), str(target), f"{seconds:.6f}"],
                check=True,
                timeout=AUDIO_DECODE_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            raise StudioError("The configured LTX-2.5 Python executable could not start.") from None
        except subprocess.CalledProcessError:
            raise StudioError(
                "The audio track could not be decoded. Use a file the LTX-2.5 environment can read."
            ) from None
        except subprocess.TimeoutExpired:
            raise StudioError("The audio track took longer than two minutes to decode.") from None

    @staticmethod
    def _command(
        python: str,
        model_paths: dict[str, Path],
        job: VideoJob,
        output_path: Path,
        image_arguments,
        enhancer_root: Path | None = None,
        edit_arguments: list[str] | None = None,
        audio_path: Path | None = None,
    ):
        if job.edit is not None:
            pipeline_module = "ltx_pipelines.ic_lora"
        elif audio_path is not None:
            pipeline_module = "ltx_pipelines.a2vid_two_stage"
        else:
            pipeline_module = "ltx_pipelines.distilled"
        # The audio pipeline runs the full model in its first stage; the other two draw with
        # the distilled checkpoint.
        transformer = model_paths["audio_transformer"] if audio_path is not None else model_paths["transformer"]
        command = [
            python,
            "-m",
            # An edit runs the in-context pipeline, which takes the same model files and reads
            # the clip it was handed; a run with a track follows the track; every other run
            # draws a clip, as it always has.
            pipeline_module,
            "--transformer-path",
            str(transformer),
            "--text-encoder-path",
            str(model_paths["text_encoder"]),
            "--video-vae-path",
            str(model_paths["video_vae"]),
            "--audio-vae-path",
            str(model_paths["audio_vae"]),
            "--duration-head-path",
            str(model_paths["duration_head"]),
            "--spatial-upsampler-path",
            str(model_paths["spatial_upsampler"]),
            "--height",
            str(job.height),
            "--width",
            str(job.width),
            "--num-frames",
            str(job.num_frames),
            "--frame-rate",
            str(job.frame_rate),
            "--prompt",
            job.prompt,
            "--output-path",
            str(output_path),
        ]
        if edit_arguments:
            command.extend(edit_arguments)
        if audio_path is not None:
            # The clip is as long as the form says: --num-frames above is already on the
            # command, and the pipeline clips the track to that length. --audio-max-duration
            # is the other way to set the length and is mutually exclusive with it.
            command.extend(
                (
                    "--audio-path",
                    str(audio_path),
                    "--num-inference-steps",
                    str(AUDIO_STEPS),
                    "--distilled-lora",
                    str(model_paths["distilled_lora"]),
                    str(DISTILLED_LORA_STRENGTH),
                )
            )
        if job.enhance and enhancer_root is not None:
            command.extend(("--enhance-prompt", "--prompt-enhancer-gemma-root", str(enhancer_root)))
        if job.seed is not None:
            command.extend(("--seed", str(job.seed)))
        for image_path, frame_index, strength in image_arguments:
            command.extend(("--image", str(image_path), str(frame_index), str(strength)))
        return command

    def _edit_arguments(self, job: VideoJob, scratch: Path) -> list[str]:
        """The adapter and the clip an edit carries, as flags, with the clip written down.

        The reference strength is 1.0, which is what the adapter was measured at: the clip is
        the whole conditioning input, and the card's own loader uses its full strength.
        """
        if job.edit is None:
            return []
        clip_path = scratch / "conditioning.mp4"
        clip_path.write_bytes(job.edit.clip)
        arguments = [
            "--lora",
            str(self._lora_path(job.edit.lora_file)),
            str(job.edit.strength),
            "--video-conditioning",
            str(clip_path),
            str(CONDITIONING_STRENGTH),
        ]
        if job.edit.stage_2_conditioning:
            # Measured: without this the second stage runs the bare checkpoint and redraws the
            # scene, and a market stall came back as a parked car.
            arguments.append("--stage-2-ic-lora")
        return arguments

    def _lora_path(self, file: str) -> Path:
        """One adapter's weights, or a refusal that says where they go."""
        if self._lora_dir is None or not self._lora_dir.is_dir():
            raise StudioError(
                "This run asked for an adapter and no lora_dir is configured under [ltx25]. "
                "Point it at the directory the adapters are downloaded into."
            )
        path = self._lora_dir / file
        if not path.is_file():
            raise StudioError(
                f"The adapter's weights are not on disk at {path}. Download them from the "
                "Lightricks LTX-2.5 Creative Lab collection with `uv run hf download <repo> "
                f"--local-dir {self._lora_dir}`."
            )
        return path

    def _execute(
        self,
        command: list[str],
        progress: Callable[[int, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        try:
            if progress or cancelled:
                self._execute_with_progress(command, progress, cancelled)
                return
            self._process_runner(
                command,
                check=True,
                timeout=RUN_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except Cancelled:
            raise
        except FileNotFoundError:
            raise StudioError("The configured LTX-2.5 Python executable could not start.") from None
        except subprocess.CalledProcessError as error:
            raise StudioError(f"The LTX-2.5 pipeline failed with exit status {error.returncode}.") from None
        except subprocess.TimeoutExpired:
            raise StudioError("The LTX-2.5 pipeline timed out after one hour.") from None

    @staticmethod
    def _execute_with_progress(
        command: list[str],
        progress: Callable[[int, int, int], None] | None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        should_cancel = cancelled or (lambda: False)
        with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, bufsize=0) as process:
            stderr = cast(BinaryIO, process.stderr)
            started = time.monotonic()
            pending = ""
            # The pipeline's own last words, kept so a crash can be read. Its output is read
            # for step markers and thrown away otherwise, which leaves a failure with nothing
            # to diagnose it: the machine runs out of memory and the page says only that the
            # run stopped.
            recent: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
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
                        raise subprocess.TimeoutExpired(command, RUN_TIMEOUT_SECONDS)
                    events = selector.select(min(0.25, remaining))
                    if not events:
                        continue
                    chunk = os.read(stderr.fileno(), 4096)
                    if not chunk:
                        selector.unregister(stderr)
                        continue
                    text = chunk.decode(errors="replace")
                    recent.extend(line for line in text.splitlines() if line.strip())
                    if progress:
                        pending += text
                        pending = _report_progress_lines(pending, progress)
            return_code = process.wait(timeout=max(0.01, RUN_TIMEOUT_SECONDS - (time.monotonic() - started)))
            if should_cancel():
                raise Cancelled("video generation was cancelled")
            if pending and progress:
                _report_progress_line(pending, progress)
            if return_code:
                raise StudioError(_crash_report(return_code, recent))


def _crash_report(return_code: int, recent: Iterable[str]) -> str:
    """What the pipeline said before it died, in the line the page will show.

    A run that dies of memory leaves no other trace: the runner reads the child's output for
    its step markers and drops the rest, so this tail is the only account a person can act on.
    """
    tail = " | ".join(list(recent)[-STDERR_TAIL_LINES:])
    if not tail:
        return f"LTX-2.5 pipeline failed with exit status {return_code} and said nothing."
    return f"LTX-2.5 pipeline failed with exit status {return_code}. Its last lines: {tail}"


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


def _report_progress_lines(pending: str, progress: Callable[[int, int, int], None]) -> str:
    lines = pending.split("\n")
    for line in lines[:-1]:
        _report_progress_line(line, progress)
    return lines[-1]


def _report_progress_line(line: str, progress: Callable[[int, int, int], None]) -> None:
    match = PROGRESS_RECORD.fullmatch(line.strip())
    if match:
        phase, step, total = (int(value) for value in match.groups())
        progress(step, total, phase)
