from abc import ABC, abstractmethod

from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway


class VideoBackendCatalogGateway(ABC):
    """Registered video models, the models the page may offer, and the selected one."""

    @abstractmethod
    def get(self, backend_id: str) -> VideoBackendGateway:
        """Return a registered video model or raise UnknownBackend."""

    @abstractmethod
    def visible_ids(self) -> tuple[str, ...]:
        """Return models in page display order."""

    @abstractmethod
    def active_id(self) -> str:
        """Return the selected video model."""

    @abstractmethod
    def set_active(self, backend_id: str) -> None:
        """Select a registered video model."""
