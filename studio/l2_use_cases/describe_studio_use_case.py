from dataclasses import dataclass

from studio.l1_entities.capabilities import Capabilities
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.boundaries.video_backend_catalog_gateway import VideoBackendCatalogGateway


@dataclass(frozen=True)
class StudioView:
    active: Capabilities
    backends: tuple[tuple[str, str, str], ...]  # (id, name, description) of each backend the page may offer
    rewrite_modes: tuple[str, ...] = ()  # the modes a prompt rewriter serves, empty when there is none
    active_video: VideoCapabilities | None = None
    video_backends: tuple[tuple[str, str, str], ...] = ()


class DescribeStudioUseCase:
    """What the page draws: the active backend's capabilities, and the backends to pick from."""

    def __init__(
        self,
        catalog: BackendCatalogGateway,
        rewriter: PromptRewriterGateway,
        video_catalog: VideoBackendCatalogGateway | None = None,
    ):
        self._catalog = catalog
        self._rewriter = rewriter
        self._video_catalog = video_catalog

    def capabilities(self, backend_id: str) -> Capabilities:
        return self._catalog.get(backend_id).capabilities()

    def execute(self) -> StudioView:
        active = self._catalog.get(self._catalog.active_id()).capabilities()
        # The description travels with the name, so the picker can say what each
        # model is rather than only what it is called.
        backends = tuple(self._offered(backend_id) for backend_id in self._catalog.visible_ids())
        # The rewriter is per backend, so a backend with none leaves the page's
        # toggle out entirely rather than offering a button that always refuses.
        video_catalog = self._video_catalog
        if video_catalog is None:
            return StudioView(active=active, backends=backends, rewrite_modes=self._rewriter.modes())
        active_video = video_catalog.get(video_catalog.active_id()).capabilities()
        video_backends = tuple(
            self._offered_video(video_catalog, backend_id) for backend_id in video_catalog.visible_ids()
        )
        return StudioView(
            active=active,
            backends=backends,
            rewrite_modes=self._rewriter.modes(),
            active_video=active_video,
            video_backends=video_backends,
        )

    def _offered(self, backend_id: str) -> tuple[str, str, str]:
        capabilities = self._catalog.get(backend_id).capabilities()
        return backend_id, capabilities.name, capabilities.description

    @staticmethod
    def _offered_video(catalog: VideoBackendCatalogGateway, backend_id: str) -> tuple[str, str, str]:
        capabilities = catalog.get(backend_id).capabilities()
        return backend_id, capabilities.name, capabilities.description
