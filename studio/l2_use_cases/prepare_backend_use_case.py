from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway


class PrepareBackendUseCase:
    """Load the active backend before the first request, so the first run pays no load."""

    def __init__(self, catalog: BackendCatalogGateway):
        self._catalog = catalog

    def execute(self) -> None:
        self._catalog.get(self._catalog.active_id()).load()
