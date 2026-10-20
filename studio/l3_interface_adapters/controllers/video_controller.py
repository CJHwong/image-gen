"""Decode the video form and keyframes before the use case sees them."""

import base64
import binascii
import io
import secrets
from collections.abc import Mapping

from PIL import Image, ImageOps, UnidentifiedImageError

from studio.l1_entities.errors import InvalidJob, UnreadableImage
from studio.l1_entities.video_capabilities import VideoAdapter, VideoCapabilities, VideoMode
from studio.l1_entities.video_job import VideoAudio, VideoEdit, VideoJob, VideoReference, VideoResult
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
    mode = capabilities.mode(_mode_id(payload.get("mode")))
    adapter = _adapter(payload, mode, capabilities) if mode.needs_clip else None
    prompt = _prompt(payload.get("prompt"))
    if adapter is not None and adapter.width and adapter.height:
        width, height = _adapter_dimensions(payload, adapter)
    else:
        width = _dimension(payload.get("width"), "width", capabilities)
        height = _dimension(payload.get("height"), "height", capabilities)
        _shape(width, height, capabilities, adapter)
    num_frames = _frame_count(payload.get("num_frames"), capabilities)
    if adapter is not None and adapter.num_frames and num_frames != adapter.num_frames:
        raise InvalidJob(f"This effect renders {adapter.num_frames} frames.")
    frame_rate = _frame_rate(payload.get("frame_rate"), capabilities)
    seed = _seed(payload.get("seed"), capabilities)
    references = _references(payload.get("references", []), num_frames, capabilities)
    return VideoJob(
        prompt,
        width,
        height,
        num_frames,
        frame_rate,
        seed,
        references,
        enhance=bool(payload.get("enhance")),
        edit=_edit(payload, adapter, capabilities) if adapter else None,
        audio=_audio(payload.get("audio"), mode, capabilities),
    )


def _mode_id(value) -> str:
    """The mode the page asked for. A page that sends none is a page before the mode switch,
    and it wants the run that draws a clip."""
    if value is None or value == "":
        return "generate"
    if not isinstance(value, str):
        raise InvalidJob("mode must be a string")
    return value


def _adapter(payload: Mapping, mode: VideoMode, capabilities: VideoCapabilities) -> VideoAdapter:
    """The adapter an edit carries. It is required, and it has to be one this mode offers: an
    adapter from the other mode is a request the form never makes."""
    adapters = capabilities.adapters_for(mode.id)
    if not adapters:
        raise InvalidJob(f"This video model offers no {mode.label.lower()} adapter.")
    wanted = payload.get("adapter")
    adapter = next((one for one in adapters if one.id == wanted), None)
    if adapter is None:
        raise InvalidJob("adapter must be one of " + ", ".join(one.id for one in adapters))
    return adapter


def _edit(payload: Mapping, adapter: VideoAdapter, capabilities: VideoCapabilities) -> VideoEdit:
    """The clip and the adapter an edit carries."""
    clip, clip_name = _clip(payload.get("clip"), capabilities)
    return VideoEdit(
        adapter=adapter.id,
        strength=_adapter_strength(payload.get("adapter_strength"), adapter),
        lora_file=adapter.file,
        clip=clip,
        clip_name=clip_name,
        stage_2_conditioning=adapter.stage_2_conditioning,
    )


def _clip(value, capabilities: VideoCapabilities) -> tuple[bytes, str]:
    if not isinstance(value, Mapping):
        raise InvalidJob("An edit needs a clip to change.")
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidJob("The clip needs a name")
    encoded = value.get("data")
    if not isinstance(encoded, str) or not encoded:
        raise InvalidJob("Could not read that clip.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidJob("Could not read that clip.") from None
    limit = int(capabilities.max_clip_megabytes * 1024 * 1024)
    if len(data) > limit:
        raise InvalidJob(f"The clip is larger than {capabilities.max_clip_megabytes:g} MB.")
    return data, name.strip()


def _audio(value, mode: VideoMode, capabilities: VideoCapabilities) -> VideoAudio | None:
    """The track a generate run follows, or None for a run that draws without one.

    The mode decides whether there is one at all: an edit takes the clip as its whole
    input, so a track that arrives with one is a request the form never makes. The suffix
    comes from the bytes, because the pipeline's decoder opens the file by its content and
    the name a browser sends is not a fact about the format.
    """
    if value is None:
        return None
    if not mode.accepts_audio:
        raise InvalidJob("An edit changes a clip. Audio is a Generate input.")
    if not isinstance(value, Mapping):
        raise InvalidJob("audio must be an object with a name and data")
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidJob("The audio track needs a name")
    encoded = value.get("data")
    if not isinstance(encoded, str) or not encoded:
        raise InvalidJob("Could not read that audio track.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidJob("Could not read that audio track.") from None
    limit = int(capabilities.max_audio_megabytes * 1024 * 1024)
    if len(data) > limit:
        raise InvalidJob(f"The audio track is larger than {capabilities.max_audio_megabytes:g} MB.")
    if not _is_audio(data):
        raise InvalidJob("That file is not audio this model reads. Use WAV, MP3, FLAC, OGG, M4A or AIFF.")
    return VideoAudio(data=data, name=name.strip())


def _is_audio(data: bytes) -> bool:
    """Whether the bytes start with a container signature this engine decodes.

    The engine sniffs the container again when it decodes, so this is a refusal before a
    long render can die on a text file, not a parser.
    """
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return True
    if data[:4] == b"fLaC":
        return True
    if data[:4] == b"OggS":
        return True
    # `say` writes an AIFF-C container, which the decoder reads as well as AIFF.
    if data[:4] == b"FORM" and data[8:12] in (b"AIFF", b"AIFC"):
        return True
    if data[4:8] == b"ftyp":
        return True
    if data[:3] == b"ID3":
        return True
    # An MPEG frame starts with eleven set bits, which covers the files that carry no tag.
    return len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0


def _adapter_strength(value, adapter: VideoAdapter) -> float:
    if value is None or value == "":
        return adapter.strength
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidJob("adapter_strength must be a number")
    if not adapter.min_strength <= value <= adapter.max_strength:
        raise InvalidJob(f"adapter_strength must be between {adapter.min_strength:g} and {adapter.max_strength:g}")
    return float(value)


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


def _adapter_dimensions(payload: Mapping, adapter: VideoAdapter) -> tuple[int, int]:
    """The card's own size, in either orientation.

    An effect is trained at one geometry, and 960 x 544 does not sit on the 64 pixel grid the
    generated clips use, so this pair is validated against the adapter rather than the ladder.
    """
    width = payload.get("width")
    height = payload.get("height")
    allowed = {(adapter.width, adapter.height), (adapter.height, adapter.width)}
    if type(width) is not int or type(height) is not int or (width, height) not in allowed:
        raise InvalidJob(f"This effect renders at {adapter.width} by {adapter.height}, in either orientation.")
    return width, height


def _shape(width: int, height: int, capabilities: VideoCapabilities, adapter: VideoAdapter | None = None) -> None:
    """A rendered shape is one the model declares, or, for an adapter that doubles the
    reference's size, exactly twice one.

    Every declared shape sits on the 64 pixel grid, so a doubled target sits on the 128 pixel
    grid, which is the pair the upscaler's card asks for. A target past the model's largest
    side was refused by `_dimension` before this check.
    """
    if any(shape.width == width and shape.height == height for shape in capabilities.shapes):
        return
    if adapter is not None and adapter.doubles_output and _half_is_declared(width, height, capabilities):
        return
    choices = ", ".join(shape.ratio for shape in capabilities.shapes)
    raise InvalidJob(f"width and height must match a supported video shape: {choices}")


def _half_is_declared(width: int, height: int, capabilities: VideoCapabilities) -> bool:
    half_width, half_height = width // 2, height // 2
    return any(shape.width == half_width and shape.height == half_height for shape in capabilities.shapes)


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
