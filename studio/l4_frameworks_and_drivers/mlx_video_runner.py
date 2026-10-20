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
from studio.l1_entities.video_job import VideoJob, VideoResult

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


def _crash_report(return_code: int, recent: deque[str]) -> str:
    tail = " | ".join(list(recent)[-TAIL_LINES:])
    if not tail:
        return f"MLX video pipeline failed with exit status {return_code} and said nothing."
    return f"MLX video pipeline failed with exit status {return_code}. Its last lines: {tail}"


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
