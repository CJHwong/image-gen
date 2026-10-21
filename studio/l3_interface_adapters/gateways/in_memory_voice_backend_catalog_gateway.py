import threading

from studio.l1_entities.errors import UnknownBackend
from studio.l2_use_cases.boundaries.voice_backend_catalog_gateway import VoiceBackendCatalogGateway


class InMemoryVoiceBackendCatalogGateway(VoiceBackendCatalogGateway):
    """The voice models built for this server and the one selected in Voice mode."""

    def __init__(self, backends, default_id, visible_ids):
        missing = [backend_id for backend_id in (default_id, *visible_ids) if backend_id not in backends]
        if missing:
            raise UnknownBackend(f"no voice backend registered as {', '.join(missing)}")
        self._backends = dict(backends)
        self._visible = tuple(visible_ids)
        self._active = default_id
        self._lock = threading.Lock()

    def get(self, backend_id):
        if backend_id not in self._backends:
            raise UnknownBackend(f"no voice backend registered as {backend_id}")
        return self._backends[backend_id]

    def visible_ids(self):
        return self._visible

    def active_id(self):
        with self._lock:
            return self._active

    def set_active(self, backend_id):
        self.get(backend_id)
        with self._lock:
            self._active = backend_id
