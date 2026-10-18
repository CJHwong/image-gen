import threading

from studio.l1_entities.errors import BackendBusy, UnknownBackend
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway


class SwitchBackendUseCase:
    """Select another visible backend and return memory from the old model.

    Only one backend fits in memory at a time: one Qwen-Image-2.1 engine alone
    peaks above 30 GB. The old backend is freed now; the new one loads on its next run.

    The engine lock is the one the runs hold, so a switch never frees a backend
    under a run. A batch between two images holds no lock; its next request
    names its backend, and the run refuses it after a switch.
    """

    def __init__(
        self,
        catalog: BackendCatalogGateway,
        engine_lock: threading.Lock,
        residency: ModelResidencyGateway,
    ):
        self._catalog = catalog
        self._engine_lock = engine_lock
        self._residency = residency

    def execute(self, backend_id: str) -> None:
        if backend_id not in self._catalog.visible_ids():
            raise UnknownBackend(f"no backend to offer as {backend_id}")
        if backend_id == self._catalog.active_id():
            return
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("Wait for the run to end, or cancel it, before you switch.")
        try:
            self._residency.activate(backend_id)
            self._catalog.set_active(backend_id)
        finally:
            self._engine_lock.release()
