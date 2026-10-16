from abc import ABC, abstractmethod

from studio.l1_entities.run_progress import RunProgress


class ProgressGateway(ABC):
    """The state of the one run in flight, shared by the request threads.

    A cancel outlives the run it landed in: a batch is a chain of separate runs,
    and a cancel that lands between two of them must still stop the batch. It is
    cleared when a run consumes it and when a fresh batch starts.
    """

    @abstractmethod
    def begin(self, label: str, kind: str = "image", request_id: str | None = None) -> None:
        """The run has started but no step has come in yet."""

    @abstractmethod
    def set_step(self, step: int, total: int, phase: int = 0) -> None: ...

    @abstractmethod
    def finish(self) -> None: ...

    @abstractmethod
    def request_cancel(self, request_id: str | None = None) -> bool:
        """Cancel an image run, or the matching video request when an ID is given."""

    @abstractmethod
    def cancel_requested(self) -> bool: ...

    @abstractmethod
    def consume_cancel(self) -> bool:
        """Read the cancel flag and clear it, as one step."""

    @abstractmethod
    def clear_cancel(self) -> None: ...

    @abstractmethod
    def snapshot(self) -> RunProgress: ...
