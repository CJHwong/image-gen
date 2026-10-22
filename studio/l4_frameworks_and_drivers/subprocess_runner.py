"""Stream and stop one owned child; engine commands and interpretation are injected."""

import os
import re
import selectors
import subprocess
import time
from collections import deque
from collections.abc import Callable
from typing import BinaryIO, cast

from studio.l1_entities.errors import Cancelled, StudioError


class SubprocessRunner:
    def execute(
        self,
        command: list[str],
        cancelled: Callable[[], bool] | None = None,
        consume: Callable[[str], None] | None = None,
        timeout_started: Callable[[], float | None] | None = None,
        *,
        environment: dict[str, str] | None = None,
        timeout_seconds: float = 3600,
        timeout_message: str = "The child process timed out.",
        cancel_message: str = "The child process was cancelled.",
        failure_message: Callable,
        tail_lines: int = 12,
    ) -> None:
        should_cancel = cancelled or (lambda: False)
        inherited = os.environ.copy()
        inherited.update(environment or {})
        with subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, bufsize=0, env=inherited
        ) as process:
            stderr = cast(BinaryIO, process.stderr)
            started = time.monotonic()
            recent: deque[str] = deque(maxlen=tail_lines)
            with selectors.DefaultSelector() as selector:
                selector.register(stderr, selectors.EVENT_READ)
                while selector.get_map():
                    if timeout_started is not None:
                        item_started = timeout_started()
                        if item_started is not None:
                            started = item_started
                    if should_cancel():
                        _stop_process(process)
                        raise Cancelled(cancel_message)
                    remaining = timeout_seconds - (time.monotonic() - started)
                    if remaining <= 0:
                        process.kill()
                        process.wait()
                        raise StudioError(timeout_message)
                    if not selector.select(min(0.25, remaining)):
                        continue
                    chunk = os.read(stderr.fileno(), 4096)
                    if not chunk:
                        selector.unregister(stderr)
                        continue
                    text = chunk.decode(errors="replace")
                    recent.extend(line for line in re.split(r"[\r\n]+", text) if line.strip())
                    if consume:
                        try:
                            consume(text)
                        except BaseException:
                            _stop_process(process)
                            raise
            return_code = process.wait(timeout=max(0.01, timeout_seconds - (time.monotonic() - started)))
            if should_cancel():
                raise Cancelled(cancel_message)
            if return_code:
                raise StudioError(failure_message(return_code, recent))


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
