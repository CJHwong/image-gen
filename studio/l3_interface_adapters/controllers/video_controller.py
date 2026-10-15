"""Decode the video form and keyframes before the use case sees them."""

import base64
import binascii
import io
from collections.abc import Mapping

from PIL import Image, ImageOps, UnidentifiedImageError

from studio.l1_entities.errors import InvalidJob, UnreadableImage
from studio.l1_entities.video_job import VideoJob, VideoReference, VideoResult
from studio.l2_use_cases.run_video_use_case import RunVideoUseCase

MAX_REFERENCES = 8
MAX_FRAMES = 361
MIN_FRAMES = 9
FRAME_GRID = 8
SIZE_GRID = 32
MIN_SIZE = 256
MAX_SIZE = 1280
FRAME_RATE = 24


class VideoController:
    def __init__(self, run: RunVideoUseCase):
        self._run = run

    def run(self, payload: Mapping) -> VideoResult:
        return self._run.execute(video_job(payload))


def video_job(payload: Mapping) -> VideoJob:
    prompt = _prompt(payload.get("prompt"))
    width = _dimension(payload.get("width"), "width")
    height = _dimension(payload.get("height"), "height")
    num_frames = _frame_count(payload.get("num_frames"))
    frame_rate = _frame_rate(payload.get("frame_rate"))
    seed = _seed(payload.get("seed"))
    references = _references(payload.get("references", []), num_frames)
    return VideoJob(prompt, width, height, num_frames, frame_rate, seed, references)


def _prompt(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidJob("A video prompt is required.")
    return value.strip()


def _dimension(value, name: str) -> int:
    if type(value) is not int:
        raise InvalidJob(f"{name} must be a whole number")
    if not MIN_SIZE <= value <= MAX_SIZE or value % SIZE_GRID:
        raise InvalidJob(f"{name} must be between {MIN_SIZE} and {MAX_SIZE}, on a {SIZE_GRID}-pixel grid")
    return value


def _frame_count(value) -> int:
    if type(value) is not int:
        raise InvalidJob("num_frames must be a whole number")
    if not MIN_FRAMES <= value <= MAX_FRAMES or (value - 1) % FRAME_GRID:
        raise InvalidJob("num_frames must be 8k + 1, between 9 and 361")
    return value


def _frame_rate(value) -> int:
    if type(value) is not int or value != FRAME_RATE:
        raise InvalidJob(f"frame_rate must be {FRAME_RATE}")
    return value


def _seed(value) -> int | None:
    if value is None or value == "":
        return None
    if type(value) is not int or not 0 <= value <= 2**32 - 1:
        raise InvalidJob("seed must be a whole number between 0 and 4294967295")
    return value


def _references(values, num_frames: int) -> tuple[VideoReference, ...]:
    if not isinstance(values, list):
        raise InvalidJob("references must be a list")
    if len(values) > MAX_REFERENCES:
        raise InvalidJob(f"A video can use at most {MAX_REFERENCES} image references")
    return tuple(_reference(value, num_frames) for value in values)


def _reference(value, num_frames: int) -> VideoReference:
    if not isinstance(value, Mapping):
        raise InvalidJob("Each video reference must be an object")
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidJob("Each video reference needs a name")
    frame_index = value.get("frame_index")
    if type(frame_index) is not int or not 0 <= frame_index < num_frames:
        raise InvalidJob(f"frame_index must be between 0 and {num_frames - 1}")
    strength = _strength(value.get("strength"))
    png, _, _ = _decode_png(value.get("image"))
    return VideoReference(name.strip(), png, frame_index, strength)


def _strength(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
        raise InvalidJob("strength must be greater than 0 and at most 1")
    return float(value)


def _decode_png(encoded: object) -> tuple[bytes, int, int]:
    if not isinstance(encoded, str) or not encoded:
        raise UnreadableImage("Could not read that video reference image.")
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))))
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    except (binascii.Error, UnidentifiedImageError, OSError, ValueError):
        raise UnreadableImage("Could not read that video reference image.") from None
    return buffer.getvalue(), image.width, image.height
