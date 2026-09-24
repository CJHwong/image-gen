import threading

from studio.l1_entities.errors import BackendBusy, UnknownBackend
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway


class SwitchBackendUseCase:
    """Make another visible backend the active one.

    Only one backend fits in memory at a time: one Qwen-Image-2.1 engine alone
    peaks above 30 GB. So the old backend is freed before the new one loads.

    The engine lock is the one the runs hold, so a switch never frees a backend
    under a run. A batch between two images holds no lock; its next request
    names its backend, and the run refuses it after a switch.
    """

    def __init__(self, catalog: BackendCatalogGateway, engine_lock: threading.Lock):
        self._catalog = catalog
        self._engine_lock = engine_lock

    def execute(self, backend_id: str) -> None:
        if backend_id not in self._catalog.visible_ids():
            raise UnknownBackend(f"no backend to offer as {backend_id}")
        if backend_id == self._catalog.active_id():
            return
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("Wait for the run to end, or cancel it, before you switch.")
        try:
            self._catalog.get(self._catalog.active_id()).release()
            self._catalog.set_active(backend_id)
            self._catalog.get(backend_id).load()
        finally:
            self._engine_lock.release()
