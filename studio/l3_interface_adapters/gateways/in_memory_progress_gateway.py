import threading

from studio.l1_entities.run_progress import RunProgress
from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway


class InMemoryProgressGateway(ProgressGateway):
    """One run at a time, so one state for the whole server.

    Request threads read it and the run writes it, so every field sits behind
    one lock.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state = RunProgress()
        self._cancel = False

    def begin(self, label):
        with self._lock:
            self._state = RunProgress(running=True, stage="preparing", label=label)

    def set_step(self, step, total):
        with self._lock:
            state = self._state
            self._state = RunProgress(running=state.running, stage="running", step=step, total=total, label=state.label)

    def finish(self):
        with self._lock:
            self._state = RunProgress()

    def request_cancel(self):
        with self._lock:
            self._cancel = True

    def cancel_requested(self):
        with self._lock:
            return self._cancel

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
                label=state.label,
                stopping=self._cancel,
            )
