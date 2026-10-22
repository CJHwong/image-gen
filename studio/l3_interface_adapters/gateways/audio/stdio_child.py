"""A long-lived engine process that answers one JSON job per line.

An engine goes into a child when it cannot live in the server process: another
dependency tree, as every engine here pins its own, or another language. The
child speaks JSON over pipes, not files and not flags. Clips as paths would put
them on disk and the text as an argument would put it in `ps`, and the server
promises neither.

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

A child that must put a clip on disk puts it in the folder named by
SCRATCH_ENV. This side makes that folder per child and removes it when the
child goes. Cancel kills a child with SIGKILL, so the child's own cleanup never
runs, and a clip it wrote to its own temp folder stayed on disk.

A child marks an error that the job caused with "kind": "input". The client
then gets a refused request, not a server failure.

A child prints `ready` on stderr once its engine is loaded. Starting a child
takes no time, but loading takes a minute, and a server that reported itself
ready before that made its first request pay for the load.
"""

import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
from collections import deque
from collections.abc import Callable

from studio.l1_entities.errors import Cancelled, InvalidJob

STEP_LINE = re.compile(rb"step (\d+)/(\d+)")
SAID_LINES = 20  # how much of the child's stderr to hold for a failure message
SAID_IN_MESSAGE = 3
READY_LINE = b"ready"
SCRATCH_ENV = "SPEECH_GEN_SCRATCH"


class StdioChild:
    def __init__(self, command: list[str]):
        self._command = command
        self._proc = None
        self._pgid = None
        self._on_step = None
        self._last_step = 0
        self._said = deque(maxlen=SAID_LINES)
        self._steps = None
        self._ready = threading.Event()
        self._loaded = False
        self._scratch = None

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
        self._remove_scratch()  # a child that died alone left its folder
        self._scratch = tempfile.mkdtemp(prefix="speech-gen-")
        self._proc = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env={**os.environ, SCRATCH_ENV: self._scratch},
        )
        # Taken while the leader is alive: start_new_session makes it the group
        # leader, so the id is its pid. Looking it up at kill time fails when the
        # leader died first, and then a wrapper that outlived it is never killed.
        # Set before the watcher starts, so no other thread reads a stale id.
        self._pgid = self._proc.pid
        self._ready = threading.Event()
        self._loaded = False
        self._steps = threading.Thread(target=self._watch_steps, args=(self._proc, self._ready), daemon=True)
        self._steps.start()

    def wait_ready(self) -> None:
        """Start the child if it is not running, and block until its engine is loaded.

        A child that ends before it says `ready` ends the wait, and its last words
        go into the error.
        """
        self.ensure()
        self._ready.wait()
        if not self._loaded:
            self.stop()
            raise RuntimeError("the engine stopped while loading" + self._last_words())

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
        # keeps the finished clip and the warm child.
        if killed.is_set():
            self._proc = None  # the kill took the engine with it
            self._drain()  # so no reader is left to append to the next job's message
            raise Cancelled(f"stopped at step {self._last_step}")
        if not answer:
            self.stop()
            self._drain()
            raise RuntimeError("the engine stopped answering" + self._last_words())
        try:
            reply = json.loads(answer)
        except ValueError:
            # The real reply may still be in the pipe, and the next job would read it.
            self.stop()
            self._drain()
            raise RuntimeError("the engine sent a reply that is not JSON" + self._last_words()) from None
        if "error" in reply:
            if reply.get("kind") == "input":
                raise InvalidJob(reply["error"])
            raise RuntimeError(reply["error"])
        return reply

    def _exchange(self, payload: dict) -> bytes:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            return b""  # the same answer as a dead child
        try:
            proc.stdin.write(json.dumps(payload).encode() + b"\n")
            proc.stdin.flush()
            return self._read_reply(proc.stdout)
        except (BrokenPipeError, OSError):
            return b""

    def _read_reply(self, stdout) -> bytes:
        """The first line that is a JSON object, or b"" when the child is gone.

        An engine library may print on stdout: mlx-audio prints its load notes
        there. Taken as the reply, such a line failed the job and put every later
        reply one job out of step. It is kept for a failure message instead.
        """
        while True:
            line = stdout.readline()
            if not line or line.lstrip().startswith(b"{"):
                return line
            self._said.append(line.decode("utf-8", "replace").strip())

    def _watch_steps(self, proc, ready: threading.Event) -> None:
        """Turn the child's step lines into progress, for the child's whole life.

        Everything else it prints is kept for the moment a job goes unanswered,
        because that is where the child says what went wrong.
        """
        for line in proc.stderr:
            if line.strip() == READY_LINE:
                self._loaded = True
                ready.set()
                continue
            match = STEP_LINE.search(line)
            if match:
                if self._on_step is not None:
                    self._last_step = int(match.group(1))
                    self._on_step(self._last_step, int(match.group(2)))
                continue
            self._said.append(line.decode("utf-8", "replace").strip())
        ready.set()  # the child has gone: a wait for it to load ends here

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
        self._remove_scratch()

    def _remove_scratch(self) -> None:
        """Remove the child's folder, and any clip in it. The child is gone, or about to start."""
        if self._scratch is None:
            return
        with contextlib.suppress(FileNotFoundError):  # already gone meets the goal
            shutil.rmtree(self._scratch)
        self._scratch = None
