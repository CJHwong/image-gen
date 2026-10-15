from abc import ABC, abstractmethod

from studio.l1_entities.video_job import VideoJob, VideoResult


class VideoBackendGateway(ABC):
    """The port used to create one video."""

    @abstractmethod
    def run(self, job: VideoJob) -> VideoResult:
        """Return the encoded video and its output settings."""
