from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway


class Ltx25BackendGateway(VideoBackendGateway):
    def __init__(self, runner):
        self._runner = runner

    def run(self, job: VideoJob) -> VideoResult:
        return self._runner.run(job)
