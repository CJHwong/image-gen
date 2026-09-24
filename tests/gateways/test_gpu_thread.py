import threading

import pytest

from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.gpu_thread import GpuThread
from studio.l3_interface_adapters.gateways.thread_confined_backend_gateway import ThreadConfinedBackendGateway
from tests.unit.fakes import FakeBackendGateway


def test_every_model_call_runs_on_one_thread():
    seen = []

    class Recording(FakeBackendGateway):
        def load(self):
            seen.append(threading.get_ident())

        def release(self):
            seen.append(threading.get_ident())

    confined = ThreadConfinedBackendGateway(Recording(), GpuThread())
    callers = [threading.Thread(target=confined.load) for _ in range(3)] + [threading.Thread(target=confined.release)]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join()
    assert len(seen) == 4 and len(set(seen)) == 1 and seen[0] != threading.get_ident()


def test_an_error_on_the_gpu_thread_reaches_the_caller():
    confined = ThreadConfinedBackendGateway(FakeBackendGateway(fail_with=RuntimeError("boom")), GpuThread())
    with pytest.raises(RuntimeError, match="boom"):
        confined.run(ImageJob(mode="generate", prompt="p", seed=1, options={"steps": 1}), None, None)
