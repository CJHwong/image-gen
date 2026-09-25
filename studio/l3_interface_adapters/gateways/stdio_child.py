"""A long-lived engine process that answers one JSON job per line.

An engine goes into a child when it cannot live in the server process: another
dependency tree (torch against MLX), or another language. The child speaks JSON
over pipes, not files and not flags. Images as paths would put them on disk and
the prompt as an argument would put it in `ps`, and the page promises neither.

The child stays up between jobs, because building a pipeline costs tens of
seconds and nothing about it depends on the job.

start_new_session puts the child in its own process group, and cancel kills
that whole group. Killing the child alone does not work: a script with a
`uv run` shebang runs as uv, with the interpreter as its child. Killing uv left
the interpreter denoising to the last step, which made cancel look like it did
nothing for 20 seconds.

A job that goes unanswered means the child died. Its stderr is the only account
of why, so the lines that are not steps are kept, and the last few go into the
error. An edit child that never started used to report nothing but "the engine
stopped answering", with `env: uv: No such file or directory` thrown away.
"""

import json
import os
import re
import signal
import subprocess
import threading
from collections import deque
from collections.abc import Callable

from studio.l1_entities.errors import Cancelled

STEP_LINE = re.compile(rb"step (\d+)/(\d+)")
SAID_LINES = 20  # how much of the child's stderr to hold for a failure message
SAID_IN_MESSAGE = 3


class StdioChild:
    def __init__(self, command: list[str]):
        self._command = command
        self._proc = None
        self._pgid = None
        self._on_step = None
        self._last_step = 0
        self._said = deque(maxlen=SAID_LINES)
        self._steps = None

    def running(self) -> bool:
        """Whether the engine is still there, its group included.

        The child starts a session, so its process group is the engine. A wrapper
        can outlive the process we started while still holding the pipes, and
        reading the process alone would call that engine dead: cancel never
        fires, a read blocks with nothing to interrupt it, and ensure() starts a
        second model on the GPU beside the first.
        """
        proc, pgid = self._proc, self._pgid
        if proc is None or pgid is None:
            return False
        proc.poll()  # reap the leader: its zombie alone would hold the group open
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True  # it is there, we just may not signal it
        return True

    def ensure(self) -> None:
        if self.running():
            return
        self._proc = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        # Taken while the leader is alive: start_new_session makes it the group
        # leader, so the id is its pid. Looking it up at kill time fails when the
        # leader died first, and then a wrapper that outlived it is never killed.
        # Set before the watcher starts, so no other thread reads a stale id.
        self._pgid = self._proc.pid
        self._steps = threading.Thread(target=self._watch_steps, args=(self._proc,), daemon=True)
        self._steps.start()

    def stop(self) -> None:
        """Kill the child and free its memory."""
        if self._proc is None:
            return
        self._kill()
        self._proc = None

    def request(
        self,
        payload: dict,
        on_step: Callable[[int, int], None],
        should_stop: Callable[[], bool],
    ) -> dict:
        """Send one job and wait for its answer.

        Raises Cancelled when should_stop() turned true and the child was killed,
        and RuntimeError when the child reports an error or dies.
        """
        self._said.clear()  # a job's reason is what the child says about that job
        self.ensure()
        self._on_step = on_step
        self._last_step = 0
        killed = threading.Event()
        answered = threading.Event()
        watcher = threading.Thread(target=self._watch_cancel, args=(should_stop, killed, answered), daemon=True)
        watcher.start()
        answer = self._exchange(payload)
        answered.set()
        watcher.join()
        # Only a kill counts as a cancel. A cancel that lands after the answer
        # keeps the finished image and the warm child.
        if killed.is_set():
            self._proc = None  # the kill took the engine with it
            self._drain()  # so no reader is left to append to the next job's message
            raise Cancelled(f"stopped at step {self._last_step}")
        if not answer:
            self.stop()
            self._drain()
            raise RuntimeError("the engine stopped answering" + self._last_words())
        reply = json.loads(answer)
        if "error" in reply:
            raise RuntimeError(reply["error"])
        return reply

    def _exchange(self, payload: dict) -> bytes:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            return b""  # the same answer as a dead child
        try:
            proc.stdin.write(json.dumps(payload).encode() + b"\n")
            proc.stdin.flush()
            return proc.stdout.readline()
        except (BrokenPipeError, OSError):
            return b""

    def _watch_steps(self, proc) -> None:
        """Turn the child's step lines into progress, for the child's whole life.

        Everything else it prints is kept for the moment a job goes unanswered,
        because that is where the child says what went wrong.
        """
        for line in proc.stderr:
            match = STEP_LINE.search(line)
            if match:
                if self._on_step is not None:
                    self._last_step = int(match.group(1))
                    self._on_step(self._last_step, int(match.group(2)))
                continue
            self._said.append(line.decode("utf-8", "replace").strip())

    def _drain(self) -> None:
        """Read out what the child left in the pipe, after the kill closed it.

        The kill comes first because a wrapper can outlive the process we started
        and hold the pipe open: only the group kill reaches it. When that kill
        lands, nothing written before it is lost, since a killed group cannot
        write again and the kernel keeps the buffer readable. When it does not
        land, this bound is what stops the read from waiting forever.
        """
        if self._steps is not None:
            self._steps.join(timeout=1.0)

    def _last_words(self) -> str:
        """What the child said before it went quiet, for the failure message."""
        said = [line for line in self._said if line]
        if not said:
            return ""
        return ". It last said: " + " | ".join(said[-SAID_IN_MESSAGE:])

    def _watch_cancel(self, should_stop, killed, answered) -> None:
        """Cancel means kill. There is no polite way to interrupt the engine.

        The watch ends with the job. The child outlives it, and a watcher left
        polling an idle child used to kill it on the next cancel of anything.
        """
        while not answered.is_set() and self.running():
            if should_stop():
                killed.set()
                self._kill()
                return
            answered.wait(0.4)

    def _kill(self) -> None:
        """Kill the child and anything it started, by the group id taken at spawn."""
        proc, pgid = self._proc, self._pgid
        if proc is None or pgid is None:
            return
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()  # the group is already gone
