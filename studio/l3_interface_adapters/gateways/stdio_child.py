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
"""

import json
import os
import re
import signal
import subprocess
import threading
from collections.abc import Callable

from studio.l1_entities.errors import Cancelled

STEP_LINE = re.compile(rb"step (\d+)/(\d+)")


class StdioChild:
    def __init__(self, command: list[str]):
        self._command = command
        self._proc = None
        self._on_step = None
        self._last_step = 0

    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

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
        threading.Thread(target=self._watch_steps, args=(self._proc,), daemon=True).start()

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
            raise Cancelled(f"stopped at step {self._last_step}")
        if not answer:
            self.stop()
            raise RuntimeError("the engine stopped answering")
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
        """Turn the child's step lines into progress, for the child's whole life."""
        for line in proc.stderr:
            match = STEP_LINE.search(line)
            if match and self._on_step is not None:
                self._last_step = int(match.group(1))
                self._on_step(self._last_step, int(match.group(2)))

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
        proc = self._proc
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()  # the group is already gone
