from abc import ABC, abstractmethod

from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway


class BackendCatalogGateway(ABC):
    """The registered backends, which of them the page may offer, and the active one."""

    @abstractmethod
    def get(self, backend_id: str) -> ImageBackendGateway:
        """Raise UnknownBackend for an id nobody registered."""

    @abstractmethod
    def visible_ids(self) -> tuple[str, ...]:
        """The backends the page may offer, in display order."""

    @abstractmethod
    def active_id(self) -> str: ...

    @abstractmethod
    def set_active(self, backend_id: str) -> None: ...
