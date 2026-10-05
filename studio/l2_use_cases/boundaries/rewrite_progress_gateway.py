from abc import ABC, abstractmethod

from studio.l1_entities.rewrite_progress import RewriteProgress


class RewriteProgressGateway(ABC):
    """The state of the one rewrite in flight, shared by the request threads.

    It is separate from the run's state, because the two jobs are separate: the
    rewriter does not fit beside an image engine, so no rewrite and no run are in
    flight at the same moment.
    """

    @abstractmethod
    def begin(self) -> None:
        """The rewrite has started but no segment has come in yet."""

    @abstractmethod
    def writing(self) -> None: ...

    @abstractmethod
    def finish(self) -> None: ...

    @abstractmethod
    def request_cancel(self) -> None: ...

    @abstractmethod
    def cancel_requested(self) -> bool: ...

    @abstractmethod
    def clear_cancel(self) -> None:
        """Drop a cancel that arrived when no rewrite was in flight.

        A rewrite that starts must not be born cancelled.
        """

    @abstractmethod
    def snapshot(self) -> RewriteProgress: ...
