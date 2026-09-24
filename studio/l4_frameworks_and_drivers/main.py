"""The composition root: builds every part and wires them. No side effects beyond that."""

import threading
from dataclasses import dataclass
from pathlib import Path

from studio.l2_use_cases.cancel_run_use_case import CancelRunUseCase
from studio.l2_use_cases.describe_studio_use_case import DescribeStudioUseCase
from studio.l2_use_cases.prepare_backend_use_case import PrepareBackendUseCase
from studio.l2_use_cases.read_progress_use_case import ReadProgressUseCase
from studio.l2_use_cases.run_image_use_case import RunImageUseCase
from studio.l2_use_cases.switch_backend_use_case import SwitchBackendUseCase
from studio.l3_interface_adapters.controllers.form_controller import FormController
from studio.l3_interface_adapters.gateways.flux2.flux2_backend_gateway import Flux2BackendGateway
from studio.l3_interface_adapters.gateways.flux2.klein_models import KleinModels
from studio.l3_interface_adapters.gateways.gpu_thread import GpuThread
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway
from studio.l3_interface_adapters.gateways.in_memory_reference_store_gateway import InMemoryReferenceStoreGateway
from studio.l3_interface_adapters.gateways.qwen21.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.qwen21.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.qwen21.qwen21_backend_gateway import Qwen21BackendGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.stub_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.thread_confined_backend_gateway import ThreadConfinedBackendGateway
from studio.l3_interface_adapters.presenters.html_presenter import HtmlPresenter
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.http_server import make_handler

PAGE = Path(__file__).with_name("web") / "page.html"


@dataclass(frozen=True)
class Studio:
    handler: type
    prepare: PrepareBackendUseCase
    catalog: InMemoryBackendCatalogGateway
    cancel: CancelRunUseCase

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
    if stub:
        backends = {backend_id: StubBackendGateway(backend.capabilities()) for backend_id, backend in backends.items()}
    return assemble_studio(backends, config.default_backend, config.visible_backends)


def assemble_studio(backends: dict, default_id: str, visible_ids: tuple[str, ...]) -> Studio:
    """Wire the page to any set of backends. Every model call runs on one GPU thread."""
    gpu = GpuThread()
    engine_lock = threading.Lock()  # held by a run and by a switch, so neither frees the other's engine
    confined = {name: ThreadConfinedBackendGateway(backend, gpu) for name, backend in backends.items()}
    catalog = InMemoryBackendCatalogGateway(confined, default_id=default_id, visible_ids=visible_ids)
    progress = InMemoryProgressGateway()
    cancel = CancelRunUseCase(progress)
    controller = FormController(
        describe=DescribeStudioUseCase(catalog),
        run=RunImageUseCase(catalog, progress, InMemoryReferenceStoreGateway(), engine_lock=engine_lock),
        read_progress=ReadProgressUseCase(progress),
        cancel=cancel,
        switch=SwitchBackendUseCase(catalog, engine_lock),
    )
    presenter = HtmlPresenter(PAGE.read_text(encoding="utf-8"))
    return Studio(
        handler=make_handler(controller, presenter),
        prepare=PrepareBackendUseCase(catalog),
        catalog=catalog,
        cancel=cancel,
    )
