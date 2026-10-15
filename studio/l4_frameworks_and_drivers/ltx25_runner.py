"""Run the official LTX-2.5 distilled pipeline and fetch its weights on first use."""

import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, cast

from studio.l1_entities.errors import StudioError
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
MODEL_REPOSITORY = "Lightricks/LTX-2.5"
RUN_TIMEOUT_SECONDS = 3600
PROGRESS_WRAPPER = """import sys
import ltx_pipelines.utils.samplers as samplers

def report_steps(iterable, *args, **kwargs):
    total = kwargs.get("total")
    if total is None:
        total = len(iterable)
    for step, value in enumerate(iterable, 1):
        yield value
        print(f"STUDIO_STEP {step} {total}", file=sys.stderr, flush=True)

samplers.tqdm = report_steps
from ltx_pipelines.distilled import main
main()
"""
PROGRESS_RECORD = re.compile(r"STUDIO_STEP (\d+) (\d+)")


class Ltx25Runner:
    def __init__(
        self,
        python_path: str,
        model_dir: str | Path,
        process_runner: Callable = subprocess.run,
        model_downloader: Callable[[Path], None] | None = None,
    ):
        self._python_path = python_path
        self._model_dir_value = str(model_dir).strip() if model_dir is not None else ""
        self._model_dir = Path(self._model_dir_value).expanduser()
        self._process_runner = process_runner
        self._model_downloader = model_downloader or self._download_model

    def run(
        self,
        job: VideoJob,
        progress: Callable[[int, int], None] | None = None,
    ) -> VideoResult:
        python = self._python()
        model_paths = self._model_paths()
        with tempfile.TemporaryDirectory(prefix="studio-ltx25-") as scratch:
            output_path = Path(scratch) / "output.mp4"
            image_arguments = self._write_references(job, Path(scratch))
            command = self._command(python, model_paths, job, output_path, image_arguments)
            if progress:
                script_path = Path(scratch) / "ltx25_progress.py"
                script_path.write_text(PROGRESS_WRAPPER, encoding="utf-8")
                command = [python, str(script_path), *command[3:]]
            self._execute(command, progress)
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

    def _model_paths(self) -> dict[str, Path]:
        if not self._model_dir_value or self._model_dir.resolve() == Path.cwd().resolve():
            raise StudioError("Set a dedicated model_dir under [ltx25] before video generation.")
        missing = [relative for relative in MODEL_FILES if not (self._model_dir / relative).is_file()]
        if missing:
            self._model_downloader(self._model_dir)
        missing = [relative for relative in MODEL_FILES if not (self._model_dir / relative).is_file()]
        if missing:
            raise StudioError(f"The LTX-2.5 local weights are incomplete: {', '.join(missing)}")
        return {name: self._model_dir / relative for name, relative in MODEL_PATHS.items()}

    @staticmethod
    def _download_model(model_dir: Path) -> None:
        from huggingface_hub import snapshot_download

        try:
            model_dir.mkdir(parents=True, exist_ok=True)
            snapshot_download(repo_id=MODEL_REPOSITORY, allow_patterns=list(MODEL_FILES), local_dir=model_dir)
        except Exception as error:
            raise StudioError(
                f"LTX-2.5 weights download failed ({type(error).__name__}). "
                "Run `hf auth login`, accept access at "
                "https://huggingface.co/Lightricks/LTX-2.5, and check the network."
            ) from None

    @staticmethod
    def _write_references(job: VideoJob, scratch: Path) -> list[tuple[Path, int, float]]:
        arguments = []
        for index, reference in enumerate(job.references):
            image_path = scratch / f"reference-{index}.png"
            image_path.write_bytes(reference.png)
            arguments.append((image_path, reference.frame_index, reference.strength))
        return arguments

    @staticmethod
    def _command(python: str, model_paths: dict[str, Path], job: VideoJob, output_path: Path, image_arguments):
        command = [
            python,
            "-m",
            "ltx_pipelines.distilled",
            "--transformer-path",
            str(model_paths["transformer"]),
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
        if job.seed is not None:
            command.extend(("--seed", str(job.seed)))
        for image_path, frame_index, strength in image_arguments:
            command.extend(("--image", str(image_path), str(frame_index), str(strength)))
        return command

    def _execute(self, command: list[str], progress: Callable[[int, int], None] | None = None) -> None:
        try:
            if progress:
                self._execute_with_progress(command, progress)
                return
            self._process_runner(
                command,
                check=True,
                timeout=RUN_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            raise StudioError("The configured LTX-2.5 Python executable could not start.") from None
        except subprocess.CalledProcessError as error:
            raise StudioError(f"The LTX-2.5 pipeline failed with exit status {error.returncode}.") from None
        except subprocess.TimeoutExpired:
            raise StudioError("The LTX-2.5 pipeline timed out after one hour.") from None

    @staticmethod
    def _execute_with_progress(command: list[str], progress: Callable[[int, int], None]) -> None:
        with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, bufsize=0) as process:
            stderr = cast(BinaryIO, process.stderr)
            started = time.monotonic()
            pending = ""
            with selectors.DefaultSelector() as selector:
                selector.register(stderr, selectors.EVENT_READ)
                while selector.get_map():
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
                    pending += chunk.decode(errors="replace")
                    pending = _report_progress_lines(pending, progress)
            return_code = process.wait(timeout=max(0.01, RUN_TIMEOUT_SECONDS - (time.monotonic() - started)))
            if pending:
                _report_progress_line(pending, progress)
            if return_code:
                raise subprocess.CalledProcessError(return_code, command)


def _report_progress_lines(pending: str, progress: Callable[[int, int], None]) -> str:
    lines = pending.split("\n")
    for line in lines[:-1]:
        _report_progress_line(line, progress)
    return lines[-1]


def _report_progress_line(line: str, progress: Callable[[int, int], None]) -> None:
    match = PROGRESS_RECORD.fullmatch(line.strip())
    if match:
        progress(int(match.group(1)), int(match.group(2)))
