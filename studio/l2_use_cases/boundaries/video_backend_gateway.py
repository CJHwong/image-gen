from abc import ABC, abstractmethod
from collections.abc import Callable

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway


class VideoBackendGateway(ModelLifecycleGateway, ABC):
    """The port used to create one video."""

    @abstractmethod
    def capabilities(self) -> VideoCapabilities:
        """Return the settings this model accepts."""

    @abstractmethod
    def run(
        self,
        job: VideoJob,
        progress: Callable[[int, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> VideoResult:
        """Return the encoded video and its output settings."""

    def run_batch(
        self,
        jobs: list[VideoJob],
        completed: Callable[[int, VideoResult], None],
        started: Callable[[int, int], None],
        progress: Callable[[int, int, int], None],
        cancelled: Callable[[], bool],
    ) -> list[VideoResult]:
        """Keep ordering and cancellation when a backend has no faster batch path."""
        results = []
        for index, job in enumerate(jobs, start=1):
            if cancelled():
                raise Cancelled("The video batch was cancelled before its next item.")
            started(index, len(jobs))
            result = self.run(job, progress, cancelled)
            completed(index, result)
            results.append(result)
        return results
