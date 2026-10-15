from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway


class StubVideoBackendGateway(VideoBackendGateway):
    """Return output metadata without an encoded file or a model call."""

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
