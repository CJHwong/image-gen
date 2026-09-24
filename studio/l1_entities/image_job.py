"""One image to make, and the image that comes back.

Images cross the core as PNG bytes. Decoding and resizing belong to the
adapters, which know what their engine wants.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

OptionValue = str | int | float  # what ParamSpec.parse returns


@dataclass(frozen=True)
class ReferenceImage:
    png: bytes
    width: int
    height: int


@dataclass(frozen=True)
class ImageJob:
    mode: str
    prompt: str
    seed: int
    options: Mapping[str, OptionValue]
    references: tuple[ReferenceImage, ...] = field(default=())


@dataclass(frozen=True)
class ImageResult:
    png: bytes
    width: int
    height: int
    seed: int
    steps: int
