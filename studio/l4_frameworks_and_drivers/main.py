"""The composition root: builds every part and wires them. No side effects beyond that."""

import threading
from dataclasses import dataclass
from pathlib import Path

from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.cancel_run_use_case import CancelRunUseCase
from studio.l2_use_cases.describe_studio_use_case import DescribeStudioUseCase
from studio.l2_use_cases.prepare_backend_use_case import PrepareBackendUseCase
from studio.l2_use_cases.read_progress_use_case import ReadProgressUseCase
from studio.l2_use_cases.rewrite_prompt_use_case import RewritePromptUseCase
from studio.l2_use_cases.run_image_use_case import RunImageUseCase
from studio.l2_use_cases.switch_backend_use_case import SwitchBackendUseCase
from studio.l3_interface_adapters.controllers.form_controller import FormController
from studio.l3_interface_adapters.gateways.flux2.flux2_backend_gateway import Flux2BackendGateway
from studio.l3_interface_adapters.gateways.flux2.klein_models import KleinModels
from studio.l3_interface_adapters.gateways.gpu_thread import GpuThread
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway
from studio.l3_interface_adapters.gateways.in_memory_reference_store_gateway import InMemoryReferenceStoreGateway
from studio.l3_interface_adapters.gateways.prompt_rewriters import (
    CatalogPromptRewriter,
    NoPromptRewriter,
    StubPromptRewriter,
)
from studio.l3_interface_adapters.gateways.qwen21.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.qwen21.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.qwen21.qwen21_backend_gateway import Qwen21BackendGateway
from studio.l3_interface_adapters.gateways.qwen21.rewriter import Qwen21Rewriter
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.stub_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.thread_confined_backend_gateway import ThreadConfinedBackendGateway
from studio.l3_interface_adapters.gateways.thread_confined_prompt_rewriter import ThreadConfinedPromptRewriter
from studio.l3_interface_adapters.presenters.html_presenter import HtmlPresenter
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.engines import require_mlx
from studio.l4_frameworks_and_drivers.http_server import make_handler

PAGE = Path(__file__).with_name("web") / "page.html"


@dataclass(frozen=True)
class Studio:
    handler: type
    prepare: PrepareBackendUseCase
    catalog: InMemoryBackendCatalogGateway
    cancel: CancelRunUseCase
    rewriter: PromptRewriterGateway | None = None

    def active_capabilities(self):
        return self.catalog.get(self.catalog.active_id()).capabilities()

    def shutdown(self) -> None:
        """Free every backend. A child engine does not share our signal handling.

        The frees wait in line on the GPU thread, behind any run, so the run is
        cancelled first. Without that, Ctrl-C waited for the image to finish.
        """
        self.cancel.execute()
        for backend_id in self.catalog.visible_ids():
            self.catalog.get(backend_id).release()
        if self.rewriter is not None:
            self.rewriter.release()


def badge(quantize: int | None) -> str:
    return f"int{quantize}" if quantize else "bf16"


def qwen21_backend(config: Config) -> Qwen21BackendGateway:
    quantize = config.backend("qwen21").get("quantize")
    return Qwen21BackendGateway(
        Qwen21Generator(quantize),
        Qwen21Edit(StdioChild([config.required("qwen21", "edit_script"), "--stdio"])),
        badge=badge(quantize),
    )


def flux2_backend(config: Config) -> Flux2BackendGateway:
    quantize = config.backend("flux2").get("quantize")
    return Flux2BackendGateway(KleinModels(config.required("flux2", "model_dir"), quantize), badge=badge(quantize))


BACKENDS = {"qwen21": qwen21_backend, "flux2": flux2_backend}

# Which backends offer a prompt rewriter, and where their weights come from. The
# rewriter is per backend, so a backend left out here reports no modes and the
# page hides its toggle rather than offering a button that always refuses.
REWRITE_MODELS = {"qwen21": lambda config: qwen21_rewrite_models(config)}
REWRITERS = {"qwen21": Qwen21Rewriter}


def qwen21_rewrite_models(config: Config) -> dict | None:
    """One rewriter model per mode: the text one rewrites a request, the image one
    reads the picture an edit will be of.

    None when studio.toml names neither. A settings file written before the
    rewriters existed has no keys for them, and that studio starts as it did,
    with no toggle, rather than refusing to boot.
    """
    settings = config.backend("qwen21")
    models = {
        "generate": settings.get("rewrite_generate_model"),
        "edit": settings.get("rewrite_edit_model"),
    }
    return models if all(models.values()) else None


def build_rewriters(config: Config) -> dict:
    built = {}
    for backend_id in config.visible_backends:
        models = REWRITE_MODELS[backend_id](config) if backend_id in REWRITE_MODELS else None
        built[backend_id] = REWRITERS[backend_id](models) if models else NoPromptRewriter()
    return built


def build_backends(config: Config) -> dict:
    """The backends the page offers, and no others: an unused one needs no settings.
    Each loads nothing until it is used."""
    unknown = [backend_id for backend_id in config.visible_backends if backend_id not in BACKENDS]
    if unknown:
        raise ConfigError(f"no backend called {', '.join(unknown)}. Known: {', '.join(BACKENDS)}")
    return {backend_id: BACKENDS[backend_id](config) for backend_id in config.visible_backends}


def create_studio(config: Config, stub: bool = False) -> Studio:
    """With `stub`, each backend keeps its form and fakes its engine: for work on the page."""
    backends = build_backends(config)
    rewriters = build_rewriters(config)
    if stub:
        backends = {backend_id: StubBackendGateway(backend.capabilities()) for backend_id, backend in backends.items()}
        rewriters = {backend_id: StubPromptRewriter() for backend_id in rewriters}
    else:
        require_mlx()
    return assemble_studio(backends, rewriters, config.default_backend, config.visible_backends)


def assemble_studio(backends: dict, rewriters: dict, default_id: str, visible_ids: tuple[str, ...]) -> Studio:
    """Wire the page to any set of backends. Every model call runs on one GPU thread."""
    gpu = GpuThread()
    engine_lock = threading.Lock()  # held by a run and by a switch, so neither frees the other's engine
    confined = {name: ThreadConfinedBackendGateway(backend, gpu) for name, backend in backends.items()}
    catalog = InMemoryBackendCatalogGateway(confined, default_id=default_id, visible_ids=visible_ids)
    rewriter = ThreadConfinedPromptRewriter(CatalogPromptRewriter(rewriters, catalog), gpu)
    progress = InMemoryProgressGateway()
    cancel = CancelRunUseCase(progress, catalog)
    controller = FormController(
        describe=DescribeStudioUseCase(catalog, rewriter),
        run=RunImageUseCase(
            catalog,
            progress,
            InMemoryReferenceStoreGateway(),
            engine_lock=engine_lock,
            rewriter=rewriter,
        ),
        read_progress=ReadProgressUseCase(progress),
        cancel=cancel,
        switch=SwitchBackendUseCase(catalog, engine_lock),
        rewrite=RewritePromptUseCase(rewriter, catalog),
    )
    presenter = HtmlPresenter(PAGE.read_text(encoding="utf-8"))
    return Studio(
        handler=make_handler(controller, presenter),
        prepare=PrepareBackendUseCase(catalog),
        catalog=catalog,
        cancel=cancel,
        rewriter=rewriter,
    )
