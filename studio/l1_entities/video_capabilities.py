"""Static facts that the video form and controller need from a model."""

from dataclasses import dataclass


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
    min_frames: int
    max_frames: int
    frame_step: int
    default_frames: int
    frame_rate: int
    max_references: int
    min_dimension: int
    max_dimension: int
    dimension_step: int
