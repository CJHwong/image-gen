"""Static facts that the video form and controller need from a model."""

from dataclasses import dataclass

from studio.l1_entities.capabilities import Template


@dataclass(frozen=True)
class VideoShape:
    ratio: str
    width: int
    height: int


@dataclass(frozen=True)
class VideoCapabilities:
    backend_id: str
    name: str
    badge: str
    description: str
    shapes: tuple[VideoShape, ...]
    default_shape_ratio: str
    min_frames: int
    max_frames: int
    frame_step: int
    duration_presets: tuple[int, ...]
    default_frames: int
    frame_rate: int
    max_references: int
    min_reference_strength: float
    max_reference_strength: float
    reference_strength_step: float
    default_reference_strength: float
    min_seed: int | None
    max_seed: int | None
    min_dimension: int
    max_dimension: int
    dimension_step: int
    # The prompt aids this model was sampled on, in the same shape the image modes use, and
    # empty for a model that was never sampled. A template whose text names the reference
    # image is offered only while the video carries one, the way an image template that names
    # the region token is offered only while the brush is available.
    templates: tuple[Template, ...] = ()
