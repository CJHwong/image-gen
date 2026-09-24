import os
import sys
import time
from pathlib import Path

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

FAKE = Path(__file__).with_name("fake_child.py")


@pytest.fixture
def child():
    # Through a shell, like the real children run through `uv run`: the engine is
    # a grandchild, and cancel must reach it.
    runner = StdioChild(["/bin/sh", "-c", f'"{sys.executable}" "{FAKE}"; exit $?'])
    yield runner
    runner.stop()


def never():
    return False


def test_a_job_comes_back_with_its_steps(child):
    steps = []
    reply = child.request({"echo": "hi", "steps": 3}, lambda step, total: steps.append((step, total)), never)
    assert reply["echo"] == "hi"
    time.sleep(0.1)
    assert steps == [(0, 3), (1, 3), (2, 3), (3, 3)]


def test_the_child_stays_up_between_jobs(child):
    first = child.request({"echo": 1}, lambda *_: None, never)
    second = child.request({"echo": 2}, lambda *_: None, never)
    assert first["pid"] == second["pid"]


def test_an_engine_error_is_raised(child):
    with pytest.raises(RuntimeError, match="out of memory"):
        child.request({"error": "out of memory"}, lambda *_: None, never)
    assert child.running()


def test_a_crash_is_raised_and_the_next_job_restarts_it(child):
    with pytest.raises(RuntimeError, match="stopped answering"):
        child.request({"crash": True}, lambda *_: None, never)
    assert child.request({"echo": "back"}, lambda *_: None, never)["echo"] == "back"


def test_cancel_kills_the_whole_group(child):
    pid = child.request({"echo": 0}, lambda *_: None, never)["pid"]
    started = time.time()
    with pytest.raises(Cancelled, match="stopped at step"):
        child.request({"steps": 50, "pause": 0.1}, lambda *_: None, lambda: time.time() - started > 0.5)
    assert time.time() - started < 2
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert not child.running()
