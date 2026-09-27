import threading

import pytest

from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.gpu_thread import GpuThread
from studio.l3_interface_adapters.gateways.thread_confined_backend_gateway import ThreadConfinedBackendGateway
from tests.support.fakes import FakeBackendGateway

JOB = ImageJob(mode="generate", prompt="a cat", seed=1, options={"steps": 2})


class Threaded(FakeBackendGateway):
    """A backend that notes the thread each call arrived on."""

    def __init__(self):
        super().__init__()
        self.threads = []

    def load(self):
        self.threads.append(threading.get_ident())
        super().load()

    def run(self, job, on_step, should_stop):
        self.threads.append(threading.get_ident())
        return super().run(job, on_step, should_stop)

    def release(self):
        self.threads.append(threading.get_ident())
        super().release()


@pytest.fixture
def parts():
    backend = Threaded()
    return ThreadConfinedBackendGateway(backend, GpuThread()), backend


def test_the_page_still_sees_the_backend_it_wraps(parts):
    confined, _ = parts
    assert confined.capabilities().backend_id == "fake"


def test_every_model_call_lands_on_one_other_thread(parts):
    # MLX binds its streams to the thread that made them, and the server answers
    # each request on a fresh thread. A load from a request thread aborts the
    # process with "There is no Stream(gpu, 1) in current thread".
    confined, backend = parts
    calls = [threading.Thread(target=confined.load) for _ in range(3)] + [threading.Thread(target=confined.release)]
    for caller in calls:
        caller.start()
    for caller in calls:
        caller.join()
    assert len(backend.threads) == 4
    assert len(set(backend.threads)) == 1
    assert backend.threads[0] != threading.get_ident()
    assert backend.events == ["load", "load", "load", "release"]


def test_a_run_goes_through_the_gpu_thread_and_comes_back(parts):
    confined, backend = parts
    steps = []
    result = confined.run(JOB, lambda step, total: steps.append(step), lambda: False)
    assert result.steps == 2
    assert steps == [1, 2]
    assert backend.jobs == [JOB]


def test_a_failure_on_the_gpu_thread_reaches_the_caller():
    backed = FakeBackendGateway(fail_with=RuntimeError("out of memory"))
    confined = ThreadConfinedBackendGateway(backed, GpuThread())
    with pytest.raises(RuntimeError, match="out of memory"):
        confined.run(JOB, None, None)
