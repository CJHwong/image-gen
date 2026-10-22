"""Values crossing the operation lifecycle boundary, independent of any transport."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OperationOutput:
    value: Any
    retained: Any


@dataclass(frozen=True)
class CompletedOperation:
    value: Any
    finished_at: float
