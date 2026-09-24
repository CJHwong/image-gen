from abc import ABC, abstractmethod
from collections.abc import Callable

from studio.l1_entities.capabilities import Capabilities
from studio.l1_entities.image_job import ImageJob, ImageResult


class ImageBackendGateway(ABC):
    """One model backend. The core runs it; the adapter knows the engine."""

    @abstractmethod
    def capabilities(self) -> Capabilities:
        """What this backend can do. Static data, cheap to call."""

    @abstractmethod
    def load(self) -> None:
        """Make the backend ready to run. Calling it again does nothing."""

    @abstractmethod
    def run(
        self,
        job: ImageJob,
        on_step: Callable[[int, int], None],
        should_stop: Callable[[], bool],
    ) -> ImageResult:
        """Make one image. Report each step as (step, total).

        Raise Cancelled once should_stop() turns true, at the latest when the
        current step ends.
        """

    @abstractmethod
    def release(self) -> None:
        """Free the model memory. The next load or run brings it back."""
