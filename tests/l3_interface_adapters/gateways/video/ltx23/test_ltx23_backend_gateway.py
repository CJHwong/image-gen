import pytest

from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l3_interface_adapters.gateways.video.ltx23.ltx23_backend_gateway import (
    Ltx23BackendGateway,
)
from studio.l3_interface_adapters.gateways.video.shared.capabilities import ltx23_mlx_capabilities


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, job, progress=None, cancelled=None):
        self.calls.append((job, progress, cancelled))
        return VideoResult(b"mp4", job.width, job.height, job.num_frames, job.frame_rate, job.seed)


def test_the_gateway_hands_the_job_to_its_runner_and_reports_the_capabilities():
    capabilities = ltx23_mlx_capabilities()
    runner = FakeRunner()
    gateway = Ltx23BackendGateway(runner)
    job = VideoJob("a cat", 384, 384, 121, 24, 7)

    def progress(step, total, phase):
        return None

    def cancelled():
        return False

    result = gateway.run(job, progress, cancelled)

    assert gateway.capabilities() == capabilities
    assert runner.calls == [(job, progress, cancelled)]
    assert result.mp4 == b"mp4"
    assert result.seed == 7


def test_release_does_nothing_because_the_process_owns_the_weights():
    gateway = Ltx23BackendGateway(FakeRunner())

    assert gateway.release() is None


def test_the_gateway_accepts_a_run_without_progress_or_cancel():
    runner = FakeRunner()
    gateway = Ltx23BackendGateway(runner)
    job = VideoJob("a cat", 384, 384, 121, 24, 7)

    gateway.run(job)

    assert runner.calls[0][0] is job
    assert runner.calls[0][1] is None
    assert runner.calls[0][2] is None


def test_the_gateway_capabilities_come_before_any_run():
    gateway = Ltx23BackendGateway(pytest.fail)

    assert gateway.capabilities().backend_id == "ltx23_mlx"


def test_the_gateway_hands_the_whole_batch_to_the_runner():
    from unittest.mock import Mock

    runner = Mock()
    runner.run_batch.return_value = ["retained"]
    gateway = Ltx23BackendGateway(runner)
    jobs = [VideoJob("cat", 384, 384, 9, 24, 7)]
    completed, started, progress, cancelled = (Mock() for _ in range(4))
    assert gateway.run_batch(jobs, completed, started, progress, cancelled) == ["retained"]
    runner.run_batch.assert_called_once_with(jobs, completed, started, progress, cancelled)
