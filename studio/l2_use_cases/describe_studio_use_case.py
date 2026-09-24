from dataclasses import dataclass

from studio.l1_entities.capabilities import Capabilities
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway


@dataclass(frozen=True)
class StudioView:
    active: Capabilities
    backends: tuple[tuple[str, str], ...]  # (id, name) of each backend the page may offer


class DescribeStudioUseCase:
    """What the page draws: the active backend's capabilities, and the backends to pick from."""

    def __init__(self, catalog: BackendCatalogGateway):
        self._catalog = catalog

    def execute(self) -> StudioView:
        active = self._catalog.get(self._catalog.active_id()).capabilities()
        backends = tuple(
            (backend_id, self._catalog.get(backend_id).capabilities().name)
            for backend_id in self._catalog.visible_ids()
        )
        return StudioView(active=active, backends=backends)
