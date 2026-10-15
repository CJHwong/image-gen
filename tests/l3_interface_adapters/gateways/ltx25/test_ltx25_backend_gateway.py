from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l3_interface_adapters.gateways.ltx25.ltx25_backend_gateway import Ltx25BackendGateway


def test_ltx25_gateway_passes_the_job_to_the_pipeline_runner():
    expected = VideoResult(b"mp4", 960, 544, 145, 24, 7)

    class FakeRunner:
        def __init__(self):
            self.job = None

        def run(self, job):
            self.job = job
            return expected

    runner = FakeRunner()
    job = VideoJob("moving clouds", 960, 544, 145, 24, 7)

    gateway = Ltx25BackendGateway(runner)
    result = gateway.run(job)

    assert runner.job == job
    assert result is expected
    assert gateway.capabilities().backend_id == "ltx25"
    gateway.release()
