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
    enhance: bool = False
    """Lengthen the prompt again inside the pipeline, with the video model's own enhancer.

    The studio's rewriter writes the longer text first, where it can be read and edited, and
    this is the model's own pass over whatever it is given. The pipeline replaces the prompt
    with what that pass writes and logs it as "Enhanced prompt: ...", which the runner reads
    and drops with the rest of the child's output, so the clip's record names the text the
    studio sent rather than the text the transformer read. Capturing that line is the way to
    close the gap, and it is measured rather than assumed: a run with the switch on logged
    the longer prompt."""


@dataclass(frozen=True)
class VideoResult:
    mp4: bytes | None
    width: int
    height: int
    num_frames: int
    frame_rate: int
    seed: int | None
    stub: bool = False
