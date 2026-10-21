import threading
from collections.abc import Callable

from studio.l1_entities.run_progress import RunProgress
from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway


class InMemoryProgressGateway(ProgressGateway):
    """One run at a time, so one state for the whole server.

    Request threads read it and the run writes it, so every field sits behind
    one lock.
    """

    def __init__(self, external_cancel: Callable[[], bool] = lambda: False):
        self._lock = threading.Lock()
        self._state = RunProgress()
        self._cancel = False
        self._external_cancel = external_cancel

    def begin(self, label, kind="image", request_id=None):
        with self._lock:
            self._state = RunProgress(
                running=True,
                stage="preparing",
                label=label,
                kind=kind,
                request_id=request_id,
            )

    def set_step(self, step, total, phase=0):
        with self._lock:
            state = self._state
            self._state = RunProgress(
                running=state.running,
                stage="running",
                step=step,
                total=total,
                phase=phase,
                label=state.label,
                kind=state.kind,
                request_id=state.request_id,
            )

    def finish(self):
        with self._lock:
            self._state = RunProgress()

    def request_cancel(self, request_id=None):
        with self._lock:
            state = self._state
            if request_id is None and state.running and state.kind == "video":
                return False
            if request_id is not None and (
                not state.running or state.kind != "video" or state.request_id != request_id
            ):
                return False
            self._cancel = True
            return True

    def cancel_requested(self):
        with self._lock:
            return self._cancel or self._external_cancel()

    def consume_cancel(self):
        with self._lock:
            wanted, self._cancel = self._cancel, False
            return wanted

    def clear_cancel(self):
        with self._lock:
            self._cancel = False

    def snapshot(self):
        with self._lock:
            state = self._state
            return RunProgress(
                running=state.running,
                stage=state.stage,
                step=state.step,
                total=state.total,
                phase=state.phase,
                label=state.label,
                stopping=self._cancel,
                kind=state.kind,
                request_id=state.request_id,
            )
