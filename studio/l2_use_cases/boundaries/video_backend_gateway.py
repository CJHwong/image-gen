from abc import ABC, abstractmethod
from collections.abc import Callable

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
