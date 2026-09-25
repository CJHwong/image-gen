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


def test_a_dead_child_says_what_it_reported_during_the_job(child):
    """The child's stderr is the only account of its death, so the message carries it."""
    with pytest.raises(RuntimeError, match="say no such file"):
        child.request({"say": "no such file", "crash": True}, lambda *_: None, never)


def test_a_failure_does_not_wait_for_a_reason_that_cannot_come():
    """A wrapper can outlive the process it started and hold the pipe open.

    The kill closes that pipe, so the wait for the child's last words ends at
    once. Reading before killing burns the whole timeout instead, every time,
    because the survivor is still holding the other end.
    """
    command = f'( sleep 2; echo "late reason" >&2 ) 1>/dev/null & exec "{sys.executable}" "{FAKE}"'
    runner = StdioChild(["/bin/sh", "-c", command])
    try:
        began = time.time()
        with pytest.raises(RuntimeError, match="stopped answering"):
            runner.request({"crash": True}, lambda *_: None, never)
        assert time.time() - began < 0.9, "the failure waited out the drain timeout"
    finally:
        runner.stop()


def test_the_engine_is_alive_while_its_group_is():
    """A wrapper can outlive the process we started and still hold its pipes."""
    command = f'( sleep 2 ) 1>/dev/null & exec "{sys.executable}" "{FAKE}"'
    runner = StdioChild(["/bin/sh", "-c", command])
    try:
        runner.request({"echo": "one", "exit": True}, lambda *_: None, never)
        time.sleep(0.3)  # let the process we started die, so only the group is left
        assert runner.running(), "the engine left the pipes to its group"
    finally:
        runner.stop()


def test_cancel_reaches_an_engine_whose_wrapper_holds_the_pipes():
    """A survivor on stdout blocks the read, so the cancel has to kill the group."""
    command = f'( sleep 5 ) & exec "{sys.executable}" "{FAKE}"'
    runner = StdioChild(["/bin/sh", "-c", command])
    try:
        runner.request({"echo": "one", "exit": True}, lambda *_: None, never)
        began = time.time()
        with pytest.raises(Cancelled, match="stopped at step"):
            runner.request({"steps": 50, "pause": 0.1}, lambda *_: None, lambda: time.time() - began > 0.5)
        assert time.time() - began < 3
    finally:
        runner.stop()


def test_a_dead_child_does_not_report_the_previous_jobs_log(child):
    """What it said about an earlier job is not the reason this one died."""
    child.request({"say": "all good"}, lambda *_: None, never)
    with pytest.raises(RuntimeError) as raised:
        child.request({"crash": True}, lambda *_: None, never)
    assert "all good" not in str(raised.value)
