"""Decode the video form and keyframes before the use case sees them."""

import base64
import binascii
import io
import secrets
from collections.abc import Mapping

from PIL import Image, ImageOps, UnidentifiedImageError

from studio.l1_entities.errors import InvalidJob, UnreadableImage
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.video_job import VideoJob, VideoReference, VideoResult
from studio.l2_use_cases.boundaries.video_backend_catalog_gateway import VideoBackendCatalogGateway
from studio.l2_use_cases.run_video_use_case import RunVideoUseCase
from studio.l2_use_cases.switch_video_backend_use_case import SwitchVideoBackendUseCase


class VideoController:
    def __init__(
        self,
        run: RunVideoUseCase,
        catalog: VideoBackendCatalogGateway,
        switch: SwitchVideoBackendUseCase,
    ):
        self._run = run
        self._catalog = catalog
        self._switch = switch

    def run(self, payload: Mapping) -> VideoResult:
        request_id = _request_id(payload.get("request_id"))
        backend_id = payload.get("backend") or self._catalog.active_id()
        if not isinstance(backend_id, str):
            raise InvalidJob("backend must be a video model id")
        backend = self._catalog.get(backend_id)
        return self._run.execute(video_job(payload, backend.capabilities()), backend_id, request_id)

    def cancel(self, payload: Mapping) -> bool:
        return self._run.cancel(_request_id(payload.get("request_id")))

    def switch(self, form: Mapping[str, str]) -> None:
        self._switch.execute(form.get("backend", ""))


def video_job(payload: Mapping, capabilities: VideoCapabilities) -> VideoJob:
    prompt = _prompt(payload.get("prompt"))
    width = _dimension(payload.get("width"), "width", capabilities)
    height = _dimension(payload.get("height"), "height", capabilities)
    _shape(width, height, capabilities)
    num_frames = _frame_count(payload.get("num_frames"), capabilities)
    frame_rate = _frame_rate(payload.get("frame_rate"), capabilities)
    seed = _seed(payload.get("seed"), capabilities)
    references = _references(payload.get("references", []), num_frames, capabilities)
    return VideoJob(prompt, width, height, num_frames, frame_rate, seed, references)


def _request_id(value) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise InvalidJob("request_id must be a non-empty string up to 128 characters")
    return value


def _prompt(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidJob("A video prompt is required.")
    return value.strip()


def _dimension(value, name: str, capabilities: VideoCapabilities) -> int:
    if type(value) is not int:
        raise InvalidJob(f"{name} must be a whole number")
    if not capabilities.min_dimension <= value <= capabilities.max_dimension or value % capabilities.dimension_step:
        raise InvalidJob(
            f"{name} must be between {capabilities.min_dimension} and {capabilities.max_dimension}, "
            f"on a {capabilities.dimension_step}-pixel grid"
        )
    return value


def _shape(width: int, height: int, capabilities: VideoCapabilities) -> None:
    if any(shape.width == width and shape.height == height for shape in capabilities.shapes):
        return
    choices = ", ".join(shape.ratio for shape in capabilities.shapes)
    raise InvalidJob(f"width and height must match a supported video shape: {choices}")


def _frame_count(value, capabilities: VideoCapabilities) -> int:
    if type(value) is not int:
        raise InvalidJob("num_frames must be a whole number")
    frame_offset = capabilities.min_frames % capabilities.frame_step
    if (
        not capabilities.min_frames <= value <= capabilities.max_frames
        or (value - frame_offset) % capabilities.frame_step
    ):
        raise InvalidJob(
            f"num_frames must be {capabilities.frame_step}k + {frame_offset}, "
            f"between {capabilities.min_frames} and {capabilities.max_frames}"
        )
    return value


def _frame_rate(value, capabilities: VideoCapabilities) -> int:
    if type(value) is not int or value != capabilities.frame_rate:
        raise InvalidJob(f"frame_rate must be {capabilities.frame_rate}")
    return value


def _seed(value, capabilities: VideoCapabilities) -> int | None:
    minimum = capabilities.min_seed
    maximum = capabilities.max_seed
    if value is None or value == "":
        if minimum is None or maximum is None:
            return None
        return minimum + secrets.randbelow(maximum - minimum + 1)
    if minimum is None or maximum is None:
        raise InvalidJob("This video model does not support a seed")
    if type(value) is not int or not minimum <= value <= maximum:
        raise InvalidJob(f"seed must be a whole number between {minimum} and {maximum}")
    return value


def _references(values, num_frames: int, capabilities: VideoCapabilities) -> tuple[VideoReference, ...]:
    if not isinstance(values, list):
        raise InvalidJob("references must be a list")
    if len(values) > capabilities.max_references:
        raise InvalidJob(f"A video can use at most {capabilities.max_references} image references")
    return tuple(_reference(value, num_frames, capabilities) for value in values)


def _reference(value, num_frames: int, capabilities: VideoCapabilities) -> VideoReference:
    if not isinstance(value, Mapping):
        raise InvalidJob("Each video reference must be an object")
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidJob("Each video reference needs a name")
    frame_index = value.get("frame_index")
    if type(frame_index) is not int or not 0 <= frame_index < num_frames:
        raise InvalidJob(f"frame_index must be between 0 and {num_frames - 1}")
    strength = _strength(value.get("strength"), capabilities)
    png, _, _ = _decode_png(value.get("image"))
    return VideoReference(name.strip(), png, frame_index, strength)


def _strength(value, capabilities: VideoCapabilities) -> float:
    minimum = capabilities.min_reference_strength
    maximum = capabilities.max_reference_strength
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
        raise InvalidJob(f"strength must be between {minimum:g} and {maximum:g}")
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
