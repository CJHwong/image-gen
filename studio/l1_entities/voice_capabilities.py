"""What a backend can do, declared as data.

A client draws its controls from this and nothing else, so a backend that lacks
a mode or a parameter simply does not show it. The same declaration checks every
job before it reaches the backend.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from studio.l1_entities.errors import InvalidJob, UnsupportedMode
from studio.l1_entities.voice_job import OptionValue


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass(frozen=True)
class ParamSpec:
    """One setting of a mode: a number in a range, one of a list, or free text."""

    id: str
    kind: str  # "number", "choice" or "text"
    default: OptionValue
    minimum: float | None = None
    maximum: float | None = None
    integer: bool = False
    step: float | None = None  # the input's increment in a client
    choices: tuple[Choice, ...] = ()
    hint: str = ""  # a line a client shows beside the input
    required: bool = False

    def parse(self, raw: str | None) -> OptionValue:
        """A raw form value as this setting's value. A blank value takes the default."""
        text = (raw or "").strip()
        if self.kind == "text":
            if self.required and not text:
                raise InvalidJob(f"{self.id} must contain text")
            return text
        if not text:
            return self.default
        if self.kind == "choice":
            return self._parse_choice(text)
        return self._parse_number(text)

    def _parse_choice(self, text: str) -> str:
        values = [choice.value for choice in self.choices]
        if text not in values:
            raise InvalidJob(f"{self.id} must be one of {', '.join(values)}")
        return text

    def _parse_number(self, text: str) -> float | int:
        try:
            number = float(text)
        except ValueError:
            raise InvalidJob(f"{self.id} must be a number") from None
        if self.integer and not number.is_integer():
            raise InvalidJob(f"{self.id} must be a whole number")
        self._check_range(number)
        return int(number) if self.integer else number

    def _check_range(self, number: float) -> None:
        low, high = self.minimum, self.maximum
        if low is not None and high is not None and not low <= number <= high:
            raise InvalidJob(f"{self.id} must be between {_plain(low)} and {_plain(high)}")
        if low is not None and number < low:
            raise InvalidJob(f"{self.id} must be at least {_plain(low)}")
        if high is not None and number > high:
            raise InvalidJob(f"{self.id} must be at most {_plain(high)}")


@dataclass(frozen=True)
class Template:
    """A starting text a client can offer, such as a tested edit instruction.

    The text names each blank as `{id}`. A client draws one input for each of `fields`,
    fills the blanks from them, and groups the templates by `group`. `length_by` names
    the field whose value divides the length of the result, for a change of speed.
    """

    name: str
    hint: str
    text: str
    group: str = ""
    fields: tuple[ParamSpec, ...] = ()
    length_by: str = ""
    target: str = "text"


@dataclass(frozen=True)
class Estimate:
    """The constants behind a time estimate: seconds of work per second of audio
    (the real-time factor), and the fixed cost of a run, such as a model load."""

    rtf: float
    overhead: float


@dataclass(frozen=True)
class ModeSpec:
    id: str
    label: str
    params: tuple[ParamSpec, ...]
    min_references: int = 0
    max_references: int = 0
    text_hint: str = ""
    text_required: str = "Some text is required."
    templates: tuple[Template, ...] = ()
    estimate: Estimate | None = None

    def parse_options(self, raw: Mapping[str, str]) -> dict[str, OptionValue]:
        """The mode's settings from a form. Fields the mode does not declare are ignored."""
        return {param.id: param.parse(raw.get(param.id)) for param in self.params}

    def check_references(self, count: int) -> None:
        if count < self.min_references:
            raise InvalidJob(f"{self.label} needs at least {_clips(self.min_references)}")
        if count > self.max_references:
            raise InvalidJob(f"{self.label} takes at most {_clips(self.max_references)}")


@dataclass(frozen=True)
class LoadingPolicy:
    policy: str = ""
    repository: str = ""
    revision: str = ""
    note: str = ""


@dataclass(frozen=True)
class Capabilities:
    backend_id: str
    name: str
    badge: str
    modes: tuple[ModeSpec, ...]
    max_batch: int
    loading: LoadingPolicy = LoadingPolicy()
    default_mode: str = "design"
    reference_sample_rate: int = 24000
    max_reference_seconds: float = 120

    def mode(self, mode_id: str) -> ModeSpec:
        for mode in self.modes:
            if mode.id == mode_id:
                return mode
        raise UnsupportedMode(f"{self.name} has no {mode_id} mode")


def _plain(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else str(number)


def _clips(count: int) -> str:
    return f"{count} reference clip" + ("" if count == 1 else "s")
