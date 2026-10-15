from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway


class StubVideoBackendGateway(VideoBackendGateway):
    """Return output metadata without an encoded file or a model call."""

    def __init__(self, capabilities: VideoCapabilities):
        self._capabilities = capabilities

    def capabilities(self) -> VideoCapabilities:
        return self._capabilities

    def run(self, job: VideoJob) -> VideoResult:
        return VideoResult(
            mp4=None,
            width=job.width,
            height=job.height,
            num_frames=job.num_frames,
            frame_rate=job.frame_rate,
            seed=job.seed,
            stub=True,
        )

    def release(self) -> None:
        pass
