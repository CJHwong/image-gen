"""A video request, its keyframes, and the encoded result."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VideoReference:
    name: str
    png: bytes
    frame_index: int
    strength: float


@dataclass(frozen=True)
class VideoJob:
    prompt: str
    width: int
    height: int
    num_frames: int
    frame_rate: int
    seed: int | None
    references: tuple[VideoReference, ...] = field(default=())


@dataclass(frozen=True)
class VideoResult:
    mp4: bytes | None
    width: int
    height: int
    num_frames: int
    frame_rate: int
    seed: int | None
    stub: bool = False
