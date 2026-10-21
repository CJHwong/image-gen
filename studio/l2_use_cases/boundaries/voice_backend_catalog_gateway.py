from abc import ABC, abstractmethod

from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway


class VoiceBackendCatalogGateway(ABC):
    """Registered voice models, the models the page may offer, and the selected one."""

    @abstractmethod
    def get(self, backend_id: str) -> VoiceBackendGateway:
        """Return a registered voice model or raise UnknownBackend."""

    @abstractmethod
    def visible_ids(self) -> tuple[str, ...]:
        """Return models in page display order."""

    @abstractmethod
    def active_id(self) -> str:
        """Return the selected voice model."""

    @abstractmethod
    def set_active(self, backend_id: str) -> None:
        """Select a registered voice model."""
