"""One clip to make, and the clip that comes back.

Audio crosses the core as WAV bytes. Decoding and resampling belong to the
adapters, which know what their engine wants.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

OptionValue = str | int | float  # what ParamSpec.parse returns


@dataclass(frozen=True)
class ReferenceAudio:
    """A clip the job carries: the voice to clone, or the audio to edit. Mono WAV."""

    wav: bytes
    seconds: float
    sample_rate: int


@dataclass(frozen=True)
class SpeechJob:
    mode: str
    text: str  # what to say, or for an edit what to change
    seed: int
    options: Mapping[str, OptionValue]
    references: tuple[ReferenceAudio, ...] = field(default=())


@dataclass(frozen=True)
class SpeechResult:
    wav: bytes
    seconds: float
    sample_rate: int
    seed: int
    steps: int
    text: str = ""
