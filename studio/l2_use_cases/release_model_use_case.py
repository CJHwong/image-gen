"""Return model memory when the user leaves its workspace."""

import threading

from studio.l1_entities.errors import BackendBusy
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway


class ReleaseModelUseCase:
    def __init__(self, engine_lock: threading.Lock, residency: ModelResidencyGateway):
        self._engine_lock = engine_lock
        self._residency = residency

    def execute(self) -> None:
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("Wait for the run to end before switching workspaces.")
        try:
            self._residency.release()
        finally:
            self._engine_lock.release()
