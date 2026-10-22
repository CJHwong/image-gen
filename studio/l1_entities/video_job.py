"""A video request, its keyframes, and the encoded result."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VideoReference:
    name: str
    png: bytes
    frame_index: int
    strength: float


@dataclass(frozen=True)
class VideoEdit:
    """A run that changes a clip it was given, and the adapter that does it.

    The adapter's own facts travel with the job because the runner is the last place that
    knows nothing: the controller reads them off the capabilities and hands them over, so the
    command line is built from the job alone.
    """

    adapter: str
    strength: float
    lora_file: str
    clip: bytes
    clip_name: str
    stage_2_conditioning: bool = False
    card: str = ""
    """The Lightricks collection the weights come from, when the studio may fetch them.
    Empty means the person placed the file themselves and the studio does not go looking."""


@dataclass(frozen=True)
class VideoAudio:
    """The track a run draws its clip against, and the name it came in under.

    The bytes stay as they arrived. The runner hands them to the engine's own environment,
    which decodes the container and writes the stereo PCM the audio VAE takes.
    """

    data: bytes
    name: str


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
    edit: VideoEdit | None = None
    """Set for a run that changes a clip, and None for one that draws a clip."""
    audio: VideoAudio | None = None
    """Set for a run whose clip follows a track. The pipeline freezes the track and returns
    it in the output unchanged, so the run reads it as timing and mood, not as a source."""
    fast_mode: bool = False
    """Use reduced transformer compute precision for this render; weights stay unchanged."""


@dataclass(frozen=True)
class VideoResult:
    mp4: bytes | None
    width: int
    height: int
    num_frames: int
    frame_rate: int
    seed: int | None
    stub: bool = False
