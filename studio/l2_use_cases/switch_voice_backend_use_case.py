"""Select a voice backend without loading its model weights."""

import threading

from studio.l1_entities.errors import BackendBusy, UnknownBackend
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway
from studio.l2_use_cases.boundaries.voice_backend_catalog_gateway import VoiceBackendCatalogGateway


class SwitchVoiceBackendUseCase:
    def __init__(
        self,
        catalog: VoiceBackendCatalogGateway,
        engine_lock: threading.Lock,
        residency: ModelResidencyGateway,
    ):
        self._catalog = catalog
        self._engine_lock = engine_lock
        self._residency = residency

    def execute(self, backend_id: str) -> None:
        if backend_id not in self._catalog.visible_ids():
            raise UnknownBackend(f"no voice backend to offer as {backend_id}")
        if backend_id == self._catalog.active_id():
            return
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("Wait for the run to end, or cancel it, before you switch.")
        try:
            self._residency.activate(backend_id)
            self._catalog.set_active(backend_id)
        finally:
            self._engine_lock.release()
