import threading

from studio.l1_entities.rewrite_progress import RewriteProgress
from studio.l2_use_cases.boundaries.rewrite_progress_gateway import RewriteProgressGateway


class InMemoryRewriteProgressGateway(RewriteProgressGateway):
    """One rewrite at a time, so one state for the whole server.

    Request threads read it and the rewriter writes it, so every field sits behind
    one lock.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state = RewriteProgress()
        self._cancel = False

    def begin(self):
        with self._lock:
            self._state = RewriteProgress(running=True, stage="preparing")

    def writing(self):
        with self._lock:
            state = self._state
            self._state = RewriteProgress(running=state.running, stage="writing")

    def finish(self):
        with self._lock:
            self._state = RewriteProgress()

    def request_cancel(self):
        with self._lock:
            self._cancel = True

    def cancel_requested(self):
        with self._lock:
            return self._cancel

    def clear_cancel(self):
        with self._lock:
            self._cancel = False

    def snapshot(self):
        with self._lock:
            state = self._state
            return RewriteProgress(
                running=state.running,
                stage=state.stage,
                stopping=self._cancel,
            )
