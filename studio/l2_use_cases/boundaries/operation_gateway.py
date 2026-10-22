"""Atomic operation reservations and bounded retained results."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class OperationGateway(ABC):
    @abstractmethod
    def begin(self, description: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def busy(self) -> bool: ...

    @abstractmethod
    def exclusive(self, action: Callable[[], None]) -> None: ...

    @abstractmethod
    def cancelling(self, operation_id: str) -> bool: ...

    @abstractmethod
    def escalate(self, operation_id: str, release: Callable[[], None]) -> None: ...

    @abstractmethod
    def active(self) -> dict[str, Any] | None: ...

    @abstractmethod
    def get(self, operation_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def recent(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def result(self, operation_id: str) -> Any: ...

    @abstractmethod
    def stopping(self, operation_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def retain(self, operation_id: str, result: object) -> None: ...

    @abstractmethod
    def append_image(self, operation_id: str, image: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def batch_started(self, operation_id, index, total): ...

    @abstractmethod
    def batch_completed(self, operation_id, result, metadata): ...

    @abstractmethod
    def item_result(self, operation_id, index): ...

    @abstractmethod
    def pause(self, operation_id: str, next_index: int) -> None: ...

    @abstractmethod
    def resume(self, operation_id: str, index: int, client_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def finish(self, operation_id: str, result: object) -> float: ...

    @abstractmethod
    def fail(self, operation_id: str, error: Exception) -> None: ...
