"""Static facts that the video form and controller need from a model."""

from dataclasses import dataclass

from studio.l1_entities.capabilities import LookRow, Template
from studio.l1_entities.errors import UnsupportedMode


@dataclass(frozen=True)
class VideoShape:
    ratio: str
    width: int
    height: int


@dataclass(frozen=True)
class VideoMode:
    """One thing the form can make, and everything it brings to the form.

    The image side declares its modes the same way, and for the same reason: what a mode takes
    and what it says are its own. `needs_clip` is the whole difference in inputs here, and the
    words follow it: an edit is handed a clip and says so on the box, the references and the
    button that starts it.
    """

    id: str
    label: str
    needs_clip: bool = False
    # A run that draws a clip can be driven by an audio track; a run that changes a clip
    # takes the clip as its whole input, so it takes no audio.
    accepts_audio: bool = False
    # The prompt aids this mode adds after the words. A mode whose text is a trigger word
    # carries none: the Look would be appended to the trigger and fight it.
    looks: tuple[LookRow, ...] = ()
    min_references: int = 0
    max_references: int = 0
    prompt_label: str = "Prompt"
    placeholder: str = ""
    """What this mode's prompt box asks for, said in the box itself rather than under the
    switch. A mode that leaves it empty keeps whatever the form ships with."""
    run_label: str = "Generate video"


@dataclass(frozen=True)
class VideoAdapter:
    """One edit recipe, and the prompt and strength that go with it.

    An empty file denotes Custom, which conditions on the clip without a task LoRA.

    The prompt is not decoration here. These adapters are triggered: four of them answer to a
    literal word, one wants an empty prompt, one wants the empty scene described rather than
    the thing to remove named. A person cannot guess that, so each adapter carries the text
    the page seeds into the box, and `prompt_mode` says what the box accepts:
    "text" for a prompt it needs, "optional" for one it reads if it is there, and "empty"
    for one it refuses.

    The sampling recipe is not a page control: `stage_2_conditioning` is a fact about how
    this adapter was measured, because the pipeline we drive samples eight sigmas at CFG 1.0
    and a card's step count or guidance would be a knob the engine ignores.
    """

    id: str
    label: str
    hint: str
    mode: str
    file: str
    prompt: str = ""
    prompt_mode: str = "text"
    strength: float = 1.0
    min_strength: float = 0.0
    max_strength: float = 2.0
    strength_step: float = 0.05
    stage_2_conditioning: bool = False
    doubles_output: bool = False
    """The card renders at twice the reference's width and height. The form asks for the
    doubled shape, and the controller accepts one for this adapter and no other. Only the
    pixel spatial upscaler does this."""
    width: int = 0
    height: int = 0
    num_frames: int = 0
    """The size and length the card trained at. Zero means the run takes the clip's own. An
    effect is trained at one geometry, and a run at another leaves the distribution: clean
    plate at 384 x 384 kept the crowd, at 1024 x 576 and 49 frames it emptied the street."""
    card: str = ""
    """The collection the effect's weights come from, when they are fetched. Empty means the
    weights are the person's own to place, and the studio does not go looking for them."""

    def __post_init__(self) -> None:
        if self.mode not in ("generate", "edit"):
            raise ValueError(f"an adapter's mode is generate or edit, not {self.mode!r}")
        if self.prompt_mode not in ("text", "optional", "empty"):
            raise ValueError(f"an adapter's prompt_mode is text, optional or empty, not {self.prompt_mode!r}")
        if self.prompt_mode == "empty" and self.prompt:
            raise ValueError(f"{self.id} refuses a prompt, so it cannot seed one")


@dataclass(frozen=True)
class VideoCapabilities:
    backend_id: str
    name: str
    badge: str
    description: str
    shapes: tuple[VideoShape, ...]
    """Every size the model renders, lowest first within each shape.

    A shape appears in the order its first size does, and the first size of the shape named
    by `default_shape_ratio` is the one the form opens on: the lowest rung, because a prompt
    is usually tried before it is worth four minutes. The form draws one button per shape and
    one per size of the shape in front.
    """
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
    # The modes the form offers, and the adapters each one can carry. Both are empty for a
    # backend that has one way of working and no adapters, which is what the form draws then:
    # no mode switch, no adapter picker.
    modes: tuple[VideoMode, ...] = ()
    adapters: tuple[VideoAdapter, ...] = ()
    max_clip_megabytes: float = 64.0
    """The largest clip an edit will take. A conditioning clip is decoded whole, so the form
    refuses one past this rather than letting a run die in the pipeline."""
    # The weights' precision, recorded with every saved clip: a file that does not say whether
    # it came from bf16 or a quantized build cannot be compared with another one later.
    precision: str = "bf16"
    max_audio_megabytes: float = 32.0
    """The largest audio track a run will take. The track crosses the request as base64, so
    the cap leaves room under the request's own 64 MB ceiling."""
    fast_mode: bool = False
    """Whether this backend accepts the optional faster, reduced-precision render path."""

    def mode(self, mode_id: str) -> VideoMode:
        """The mode with this id. A backend with no modes has one, and it is generate."""
        if not self.modes:
            return VideoMode("generate", "Generate")
        for mode in self.modes:
            if mode.id == mode_id:
                return mode
        raise UnsupportedMode(f"This video model has no {mode_id} mode.")

    def adapters_for(self, mode_id: str) -> tuple[VideoAdapter, ...]:
        return tuple(adapter for adapter in self.adapters if adapter.mode == mode_id)
