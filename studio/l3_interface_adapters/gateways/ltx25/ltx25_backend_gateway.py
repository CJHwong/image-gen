from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l3_interface_adapters.gateways.ltx25.capabilities import ltx25_capabilities


class Ltx25BackendGateway(VideoBackendGateway):
    def __init__(self, runner):
        self._runner = runner

    def capabilities(self):
        return ltx25_capabilities()

    def run(self, job: VideoJob) -> VideoResult:
        return self._runner.run(job)

    def release(self) -> None:
        # The pipeline process owns the model and exits after each video.
        pass
