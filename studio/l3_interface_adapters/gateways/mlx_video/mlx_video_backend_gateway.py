"""The video backend that drives the MLX q8 packs."""

from collections.abc import Callable

from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway


class MlxVideoBackendGateway(VideoBackendGateway):
    def __init__(self, capabilities: VideoCapabilities, runner):
        self._capabilities = capabilities
        self._runner = runner

    def capabilities(self) -> VideoCapabilities:
        return self._capabilities

    def run(
        self,
        job: VideoJob,
        progress: Callable[[int, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> VideoResult:
        return self._runner.run(job, progress, cancelled)

    def run_batch(self, jobs, completed, started, progress, cancelled) -> list[VideoResult]:
        return self._runner.run_batch(jobs, completed, started, progress, cancelled)

    def release(self) -> None:
        # The pipeline process owns the weights and exits after each clip.
        pass
