from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l3_interface_adapters.gateways.ltx25.ltx25_backend_gateway import Ltx25BackendGateway


def test_ltx25_gateway_passes_the_job_to_the_pipeline_runner():
    expected = VideoResult(b"mp4", 960, 544, 145, 24, 7)

    class FakeRunner:
        def __init__(self):
            self.job = None

        def run(self, job, progress=None):
            self.job = job
            self.progress = progress
            if progress:
                progress(2, 4)
            return expected

    runner = FakeRunner()
    job = VideoJob("moving clouds", 960, 544, 145, 24, 7)
    reports = []

    def progress(step, total):
        reports.append((step, total))

    gateway = Ltx25BackendGateway(runner)
    result = gateway.run(job, progress)

    assert runner.job == job
    assert runner.progress is progress
    assert reports == [(2, 4)]
    assert result is expected
    assert gateway.capabilities().backend_id == "ltx25"
    gateway.release()
