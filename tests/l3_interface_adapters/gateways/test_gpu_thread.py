import threading

import pytest

from studio.l3_interface_adapters.gateways.gpu_thread import GpuThread


def boom():
    raise RuntimeError("out of memory")


def test_every_call_runs_on_one_thread():
    # The HTTP server answers each request on a fresh thread. The model has to
    # see one thread for its whole life, or MLX finds no stream for it.
    gpu = GpuThread()
    seen = []
    callers = [threading.Thread(target=lambda: seen.append(gpu.call(threading.get_ident))) for _ in range(3)]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join()
    assert len(seen) == 3 and len(set(seen)) == 1 and seen[0] != threading.get_ident()


def test_a_call_answers_what_the_function_returned():
    assert GpuThread().call(lambda width, height: width * height, 4, 3) == 12


def test_an_error_on_the_gpu_thread_reaches_the_caller():
    with pytest.raises(RuntimeError, match="out of memory"):
        GpuThread().call(boom)


def test_the_thread_serves_the_next_call_after_a_failure():
    # A raised call must not take the one thread down: every later model call
    # would block forever on a wait nobody sets.
    gpu = GpuThread()
    with pytest.raises(RuntimeError):
        gpu.call(boom)
    assert gpu.call(lambda: "still here") == "still here"
