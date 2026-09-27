from dataclasses import dataclass

from studio.l1_entities.capabilities import Capabilities
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway


@dataclass(frozen=True)
class StudioView:
    active: Capabilities
    backends: tuple[tuple[str, str], ...]  # (id, name) of each backend the page may offer
    rewrite_modes: tuple[str, ...] = ()  # the modes a prompt rewriter serves, empty when there is none


class DescribeStudioUseCase:
    """What the page draws: the active backend's capabilities, and the backends to pick from."""

    def __init__(self, catalog: BackendCatalogGateway, rewriter: PromptRewriterGateway):
        self._catalog = catalog
        self._rewriter = rewriter

    def execute(self) -> StudioView:
        active = self._catalog.get(self._catalog.active_id()).capabilities()
        backends = tuple(
            (backend_id, self._catalog.get(backend_id).capabilities().name)
            for backend_id in self._catalog.visible_ids()
        )
        # The rewriter is per backend, so a backend with none leaves the page's
        # toggle out entirely rather than offering a button that always refuses.
        return StudioView(active=active, backends=backends, rewrite_modes=self._rewriter.modes())
