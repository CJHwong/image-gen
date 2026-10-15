import threading
from collections.abc import Mapping

from studio.l1_entities.errors import UnknownBackend
from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway


class InMemoryModelResidencyGateway(ModelResidencyGateway):
    """Release the previous owner before a new backend can use model memory."""

    def __init__(self, backends: Mapping[str, ModelLifecycleGateway]):
        self._backends = dict(backends)
        self._active_id: str | None = None
        self._lock = threading.RLock()

    def activate(self, backend_id: str) -> None:
        with self._lock:
            if backend_id not in self._backends:
                raise UnknownBackend(f"no runtime registered as {backend_id}")
            if backend_id == self._active_id:
                return
            self.release()
            self._active_id = backend_id

    def release(self) -> None:
        with self._lock:
            if self._active_id is None:
                return
            self._backends[self._active_id].release()
            self._active_id = None

    def active_id(self) -> str | None:
        with self._lock:
            return self._active_id
