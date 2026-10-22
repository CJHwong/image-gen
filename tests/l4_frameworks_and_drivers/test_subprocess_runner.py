import subprocess
import sys
from typing import Any, cast

from studio.l4_frameworks_and_drivers.subprocess_runner import _stop_process


def test_stop_process_leaves_a_child_that_already_exited():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()

    _stop_process(process)


def test_stop_process_ignores_a_process_that_is_already_gone():
    class Gone:
        def poll(self):
            return None

        def terminate(self):
            raise ProcessLookupError

    _stop_process(cast(Any, Gone()))


def test_stop_process_kills_a_child_that_ignores_terminate():
    class Stubborn:
        def __init__(self):
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("child", timeout)
            return 0

        def kill(self):
            self.killed = True

    child = Stubborn()

    _stop_process(cast(Any, child))

    assert child.killed is True


def test_generic_driver_streams_without_a_consumer_and_preserves_caller_environment(monkeypatch):
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    monkeypatch.setenv("STUDIO_TEST_CHILD_VALUE", "parent")
    command = [
        sys.executable,
        "-c",
        "import os,sys; sys.stderr.write(os.environ['STUDIO_TEST_CHILD_VALUE']); raise SystemExit(2)",
    ]
    import os

    import pytest

    from studio.l1_entities.errors import StudioError

    with pytest.raises(StudioError, match="2: child"):
        SubprocessRunner().execute(
            command,
            environment={"STUDIO_TEST_CHILD_VALUE": "child"},
            failure_message=lambda code, tail: f"{code}: {' '.join(tail)}",
        )
    assert os.environ["STUDIO_TEST_CHILD_VALUE"] == "parent"
