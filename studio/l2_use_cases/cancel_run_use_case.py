"""Stop the run in flight, and free the engine if the stop is never seen.

The cancel flag only works where the engine looks at it: at a step for the engine
inside this process, and in the child gateway's own watcher. One flag and one thread
cannot rule out a stop that is never seen, and then the run keeps going while the
button appears to do nothing. So the flag goes first, because it stops a run that is
looking and leaves a warm engine warm, and the engine is freed outright if the run is
still in flight after `patience` seconds.
"""

import threading
import time
from collections.abc import Callable

from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway

# An engine inside this process can only look at a step, and the encode before the first
# one is measured at 30 to 90 seconds, so a cancel during it is unobservable rather than
# ignored. Freeing the engine costs a reload on the next run, so the net has to outlast
# that encode before it is worth doing: this sits above the worst measured one.
PATIENCE_SECONDS = 120.0


class CancelRunUseCase:
    """Stop the run in flight, and free the engine if that is not enough."""

    def __init__(
        self,
        progress: ProgressGateway,
        catalog: BackendCatalogGateway,
        patience: float = PATIENCE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ):
        self._progress = progress
        self._catalog = catalog
        self._patience = patience
        self._clock = clock
        self._wait = wait
        self._escalating = False
        self._lock = threading.Lock()

    def execute(self) -> None:
        self._progress.request_cancel()
        with self._lock:
            if self._escalating:
                return  # one watch per cancel is enough
            self._escalating = True
        threading.Thread(target=self._free_if_unseen, daemon=True).start()

    def _free_if_unseen(self) -> None:
        try:
            began = self._clock()
            while self._clock() - began < self._patience:
                if not self._progress.snapshot().running:
                    return  # it stopped, so the engine stays warm
                self._wait(0.25)
            if not self._progress.snapshot().running:
                return
            # Free the engine. A child is killed outright; an engine inside this process
            # frees its model, and the flag stops it at the next step either way.
            self._catalog.get(self._catalog.active_id()).release()
        finally:
            with self._lock:
                self._escalating = False
