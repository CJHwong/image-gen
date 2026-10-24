"""The composition root: builds every part and wires them. No side effects beyond that."""

import threading
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.cancel_rewrite_use_case import CancelRewriteUseCase
from studio.l2_use_cases.cancel_run_use_case import CancelRunUseCase
from studio.l2_use_cases.complete_operation_use_case import CompleteOperationUseCase
from studio.l2_use_cases.describe_studio_use_case import DescribeStudioUseCase
from studio.l2_use_cases.prepare_batch_use_case import PrepareBatchUseCase
from studio.l2_use_cases.read_progress_use_case import ReadProgressUseCase
from studio.l2_use_cases.read_rewrite_progress_use_case import ReadRewriteProgressUseCase
from studio.l2_use_cases.release_model_use_case import ReleaseModelUseCase
from studio.l2_use_cases.rewrite_prompt_use_case import RewritePromptUseCase
from studio.l2_use_cases.run_image_use_case import RunImageUseCase
from studio.l2_use_cases.run_video_use_case import RunVideoUseCase
from studio.l2_use_cases.run_voice_use_case import RunVoiceUseCase
from studio.l2_use_cases.switch_backend_use_case import SwitchBackendUseCase
from studio.l2_use_cases.switch_video_backend_use_case import SwitchVideoBackendUseCase
from studio.l2_use_cases.switch_voice_backend_use_case import SwitchVoiceBackendUseCase
from studio.l3_interface_adapters.api.json_api import JsonApi
from studio.l3_interface_adapters.controllers.form_controller import FormController
from studio.l3_interface_adapters.controllers.video_controller import VideoController
from studio.l3_interface_adapters.controllers.voice_controller import VoiceController
from studio.l3_interface_adapters.gateways.audio.auk.auk_backend_gateway import AukBackendGateway
from studio.l3_interface_adapters.gateways.audio.auk_flash.auk_flash_backend_gateway import AukFlashBackendGateway
from studio.l3_interface_adapters.gateways.audio.drama3.drama3_backend_gateway import Drama3BackendGateway
from studio.l3_interface_adapters.gateways.audio.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.audio.stub_voice_backend_gateway import StubVoiceBackendGateway
from studio.l3_interface_adapters.gateways.gpu_thread import GpuThread
from studio.l3_interface_adapters.gateways.image.flux2.flux2_backend_gateway import Flux2BackendGateway
from studio.l3_interface_adapters.gateways.image.flux2.klein_models import KleinModels
from studio.l3_interface_adapters.gateways.image.qwen21.qwen21_backend_gateway import Qwen21BackendGateway
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.official_qwen_turbo_backend_gateway import (
    OfficialQwenTurboBackendGateway,
)
from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter import Qwen21Rewriter
from studio.l3_interface_adapters.gateways.image.shared import qwen21_turbo_schedule
from studio.l3_interface_adapters.gateways.image.stub_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.image.thread_confined_backend_gateway import ThreadConfinedBackendGateway
from studio.l3_interface_adapters.gateways.image.viggle_turbo.viggle_turbo_backend_gateway import (
    ViggleTurboBackendGateway,
)
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from studio.l3_interface_adapters.gateways.in_memory_model_residency_gateway import (
    InMemoryModelResidencyGateway,
)
from studio.l3_interface_adapters.gateways.in_memory_operation_gateway import InMemoryOperationGateway
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway
from studio.l3_interface_adapters.gateways.in_memory_reference_store_gateway import InMemoryReferenceStoreGateway
from studio.l3_interface_adapters.gateways.in_memory_rewrite_progress_gateway import (
    InMemoryRewriteProgressGateway,
)
from studio.l3_interface_adapters.gateways.in_memory_video_backend_catalog_gateway import (
    InMemoryVideoBackendCatalogGateway,
)
from studio.l3_interface_adapters.gateways.in_memory_voice_backend_catalog_gateway import (
    InMemoryVoiceBackendCatalogGateway,
)
from studio.l3_interface_adapters.gateways.prompt_rewriters import (
    CatalogPromptRewriter,
    NoPromptRewriter,
    StubPromptRewriter,
)
from studio.l3_interface_adapters.gateways.thread_confined_prompt_rewriter import ThreadConfinedPromptRewriter
from studio.l3_interface_adapters.gateways.video.gemma3.gemma3_prompt_rewriter_gateway import (
    Gemma3PromptRewriterGateway,
)
from studio.l3_interface_adapters.gateways.video.gemma3.prompt_enhancer import Gemma3PromptEnhancer
from studio.l3_interface_adapters.gateways.video.ltx23.ltx23_backend_gateway import Ltx23BackendGateway
from studio.l3_interface_adapters.gateways.video.ltx25.ltx25_backend_gateway import Ltx25BackendGateway
from studio.l3_interface_adapters.gateways.video.ltx_runtime.runner import MlxVideoRunner
from studio.l3_interface_adapters.gateways.video.stub_video_backend_gateway import StubVideoBackendGateway
from studio.l3_interface_adapters.presenters.html_presenter import HtmlPresenter
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.engines import require_mlx
from studio.l4_frameworks_and_drivers.http_server import make_handler
from studio.l4_frameworks_and_drivers.model_plugins import ModelPlugins
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

PAGE = Path(__file__).with_name("web") / "page.html"


@dataclass(frozen=True)
class Studio:
    handler: type
    catalog: InMemoryBackendCatalogGateway
    video_catalog: InMemoryVideoBackendCatalogGateway | None
    residency: InMemoryModelResidencyGateway
    cancel: CancelRunUseCase
    rewriter: PromptRewriterGateway | None = None

    video_rewriter: PromptRewriterGateway | None = None

    def active_capabilities(self):
        return self.catalog.get(self.catalog.active_id()).capabilities()

    def shutdown(self) -> None:
        """Free the one resident model and the prompt rewriter.

        The frees wait in line on the GPU thread, behind any run, so the run is
        cancelled first. Without that, Ctrl-C waited for the image to finish.
        """
        self.cancel.execute()
        self.residency.release()
        if self.rewriter is not None:
            self.rewriter.release()
        if self.video_rewriter is not None:
            self.video_rewriter.release()


def badge(quantize: int | None) -> str:
    return f"int{quantize}" if quantize else "bf16"


def qwen21_backend(config: Config) -> Qwen21BackendGateway:
    quantize = config.backend("qwen21").get("quantize")
    return Qwen21BackendGateway(Qwen21Generator(quantize), Qwen21Edit(quantize), badge=badge(quantize))


def qwen21_turbo_backend(config: Config) -> OfficialQwenTurboBackendGateway:
    """The official Turbo checkpoint, which samples the sigma table it ships.

    The generator is told the schedule by name, and the gateway registers it when a
    run starts. Not here: building a backend must not import mflux, because the stub
    builds every backend on machines that cannot run a model at all, and its whole
    point is that the page still works there.
    """
    settings = config.backend("qwen21_turbo")
    from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit_input_cache import cache_edit_inputs
    from studio.l3_interface_adapters.gateways.image.qwen_runtime.encoder_restore import restore_text_encoder
    from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import active_mlx_memory

    model_dir = config.required("qwen21_turbo", "model_dir")
    quantize = settings.get("quantize")
    return OfficialQwenTurboBackendGateway(
        Qwen21Generator(
            quantize,
            model_path=model_dir,
            scheduler=qwen21_turbo_schedule.SCHEDULER_NAME,
            restore_encoder=partial(restore_text_encoder, model_path=model_dir, quantize=quantize),
        ),
        Qwen21Edit(quantize, model_path=model_dir, prepare_model=cache_edit_inputs),
        badge=badge(quantize),
        model_dir=model_dir,
        memory_scope=active_mlx_memory,
    )


def flux2_backend(config: Config) -> Flux2BackendGateway:
    quantize = config.backend("flux2").get("quantize")
    return Flux2BackendGateway(KleinModels(config.required("flux2", "model_dir"), quantize), badge=badge(quantize))


def viggle_turbo_backend(config: Config) -> ViggleTurboBackendGateway:
    """The two models qwen21 drives, built with Viggle's adapter and its schedule.

    The generator is told to sample the turbo schedule, which its command accepts.
    The edit half cannot be told, so its gateway supplies the schedule another way.

    The adapter's file is checked when this backend loads, not here. A backend is
    built whether or not it is used, and the stub builds every one of them, so a
    check here would stop page work on a machine that never asked for the model.
    """
    settings = config.backend("viggle_turbo")
    lora_path = config.required("viggle_turbo", "lora_path")
    quantize = settings.get("quantize")
    return ViggleTurboBackendGateway(
        Qwen21Generator(quantize, lora_path=lora_path, scheduler="viggle_turbo"),
        Qwen21Edit(quantize, lora_path=lora_path),
        badge=badge(quantize),
        lora_path=lora_path,
    )


BACKENDS = {
    "qwen21": qwen21_backend,
    "qwen21_turbo": qwen21_turbo_backend,
    "flux2": flux2_backend,
    "viggle_turbo": viggle_turbo_backend,
}


def ltx25_mlx_backend(config: Config, enhanced_prompt=None) -> Ltx25BackendGateway:
    return Ltx25BackendGateway(
        _mlx_video_runner(config, "model_ltx25", keyframe_two_stage=False, enhanced_prompt=enhanced_prompt)
    )


def ltx23_mlx_backend(config: Config, enhanced_prompt=None) -> Ltx23BackendGateway:
    return Ltx23BackendGateway(
        _mlx_video_runner(config, "model_ltx23", keyframe_two_stage=True, enhanced_prompt=enhanced_prompt)
    )


def _mlx_video_runner(
    config: Config, model_key: str, *, keyframe_two_stage: bool, enhanced_prompt=None
) -> MlxVideoRunner:
    settings = config.backend("mlx_video")
    model = str(settings.get(model_key, ""))
    return MlxVideoRunner(
        settings,
        model,
        True,
        keyframe_two_stage,
        model_key=model_key,
        enhanced_prompt=enhanced_prompt,
        execute_process=SubprocessRunner().execute,
    )


VIDEO_BACKENDS = {
    "ltx25_mlx": ltx25_mlx_backend,
    "ltx23_mlx": ltx23_mlx_backend,
}

# Which backends offer a prompt rewriter, and where their weights come from. The
# rewriter is a model of its own and does not read the image engine at all, so
# every backend driving this model family offers the same two. A backend left out
# here reports no modes and the page hides its toggle rather than offering a button
# that always refuses.
REWRITERS = {"qwen21": Qwen21Rewriter, "qwen21_turbo": Qwen21Rewriter, "viggle_turbo": Qwen21Rewriter}


def qwen21_rewrite_models(config: Config, backend_id: str) -> dict | None:
    """One rewriter model per mode: the text one rewrites a request, the image one
    reads the picture an edit will be of.

    Read from the section of the backend that will use it, since that is where a
    reader would look for it. None when studio.toml names neither. A settings file
    written before the rewriters existed has no keys for them, and that studio
    starts as it did, with no toggle, rather than refusing to boot.
    """
    settings = config.backend(backend_id)
    models = {
        "generate": settings.get("rewrite_generate_model"),
        "edit": settings.get("rewrite_edit_model"),
    }
    return models if all(models.values()) else None


def build_rewriters(config: Config, plugins: ModelPlugins | None = None, stub: bool = False) -> dict:
    built = {}
    for backend_id in config.visible_backends:
        if plugins and backend_id in plugins.ids("image"):
            built[backend_id] = plugins.rewriter("image", backend_id, config, stub)
        else:
            models = qwen21_rewrite_models(config, backend_id) if backend_id in REWRITERS else None
            built[backend_id] = REWRITERS[backend_id](models) if models else NoPromptRewriter()
    return built


def build_backends(config: Config, plugins: ModelPlugins | None = None, stub: bool = False) -> dict:
    """The backends the page offers, and no others: an unused one needs no settings.
    Each loads nothing until it is used."""
    registry = {**BACKENDS, **plugin_factories(plugins, "image", stub)}
    unknown = [backend_id for backend_id in config.visible_backends if backend_id not in registry]
    if unknown:
        raise ConfigError(f"no backend called {', '.join(unknown)}. Known: {', '.join(registry)}")
    return {backend_id: registry[backend_id](config) for backend_id in config.visible_backends}


def build_video_backends(
    config: Config, enhanced_prompt=None, plugins: ModelPlugins | None = None, stub: bool = False
) -> dict:
    registry = {**VIDEO_BACKENDS, **plugin_factories(plugins, "video", stub)}
    unknown = [backend_id for backend_id in config.visible_video_backends if backend_id not in registry]
    if unknown:
        raise ConfigError(f"no video backend called {', '.join(unknown)}. Known: {', '.join(registry)}")
    return {
        backend_id: registry[backend_id](config, enhanced_prompt=enhanced_prompt)
        for backend_id in config.visible_video_backends
    }


def voice_auk_backend(config: Config) -> AukBackendGateway:
    return AukBackendGateway(_auk_child(config, "auk_base", "base"))


def voice_auk_flash_backend(config: Config) -> AukFlashBackendGateway:
    return AukFlashBackendGateway(_auk_child(config, "auk", "flash"))


def _auk_child(config: Config, backend_id: str, variant: str) -> StdioChild:
    child_path = Path(__file__).parents[1] / "l3_interface_adapters/gateways/audio/auk_runtime/auk_child.py"
    settings = {**config.backend("auk"), **config.backend(backend_id)}
    return StdioChild(["uv", "run", "--script", str(settings.get("child_script", child_path)), "--variant", variant])


def voice_drama_backend(config: Config):
    child_path = Path(__file__).parents[1] / "l3_interface_adapters/gateways/audio/drama3/drama3_child.py"
    settings = config.backend("drama3")
    script = str(settings.get("child_script", child_path))
    python = settings.get("python_path")
    command = [str(python), script] if python else ["uv", "run", "--script", script]
    return Drama3BackendGateway(StdioChild(command))


VOICE_BACKENDS = {
    "auk": voice_auk_flash_backend,
    "auk_base": voice_auk_backend,
    "drama3": voice_drama_backend,
}


def build_voice_backends(config: Config, plugins: ModelPlugins | None = None, stub: bool = False):
    registry = {**VOICE_BACKENDS, **plugin_factories(plugins, "voice", stub)}
    unknown = [name for name in config.visible_voice_backends if name not in registry]
    if unknown:
        raise ConfigError(f"no voice backend called {', '.join(unknown)}. Known: {', '.join(registry)}")
    return {name: registry[name](config) for name in config.visible_voice_backends}


def discover_plugins() -> ModelPlugins:
    return ModelPlugins({"image": BACKENDS, "video": VIDEO_BACKENDS, "voice": VOICE_BACKENDS})


def plugin_factories(plugins: ModelPlugins | None, kind: str, stub: bool) -> dict:
    return {name: partial(plugins.build, kind, name, stub=stub) for name in plugins.ids(kind)} if plugins else {}


def create_studio(
    config: Config,
    stub: bool = False,
    plugins: ModelPlugins | None = None,
    allowed_origins: tuple[str, ...] = (),
) -> Studio:
    """With `stub`, each backend keeps its form and fakes its engine: for work on the page.
    `allowed_origins` are the pages at another address that may post, such as a proxy."""
    plugins = plugins if plugins is not None else discover_plugins()
    backends = build_backends(config, plugins, stub)
    enhancer = Gemma3PromptEnhancer(config.backend("mlx_video"), SubprocessRunner().execute)
    video_backends = build_video_backends(config, enhancer.is_enhanced, plugins, stub)
    video_rewriter = StubPromptRewriter() if stub else Gemma3PromptRewriterGateway(enhancer)
    voice_backends = build_voice_backends(config, plugins, stub)
    rewriters = build_rewriters(config, plugins, stub)
    video_rewriters = {
        name: plugins.rewriter("video", name, config, stub) if name in plugins.ids("video") else video_rewriter
        for name in video_backends
    }
    if stub:
        voice_backends = {
            name: StubVoiceBackendGateway(capabilities=backend.capabilities())
            for name, backend in voice_backends.items()
        }
        backends = {backend_id: StubBackendGateway(backend.capabilities()) for backend_id, backend in backends.items()}
        rewriters = {
            backend_id: rewriters[backend_id] if backend_id in plugins.ids("image") else StubPromptRewriter()
            for backend_id in rewriters
        }
        video_backends = {
            backend_id: StubVideoBackendGateway(backend.capabilities())
            for backend_id, backend in video_backends.items()
        }
    elif any(
        name in BACKENDS or name in VIDEO_BACKENDS or name in VOICE_BACKENDS
        for name in (*backends, *video_backends, *voice_backends)
    ):
        require_mlx()
    return assemble_studio(
        backends,
        rewriters,
        config.default_backend,
        config.visible_backends,
        video_backends=video_backends,
        default_video_id=config.default_video_backend,
        visible_video_ids=config.visible_video_backends,
        voice_backends=voice_backends,
        default_voice_id=config.default_voice_backend,
        visible_voice_ids=config.visible_voice_backends,
        video_rewriters=video_rewriters,
        allowed_origins=allowed_origins,
    )


def assemble_studio(
    backends: dict,
    rewriters: dict,
    default_id: str,
    visible_ids: tuple[str, ...],
    video_backends: dict | None = None,
    default_video_id: str | None = None,
    visible_video_ids: tuple[str, ...] = (),
    voice_backend=None,
    voice_backends=None,
    default_voice_id="auk",
    visible_voice_ids=(),
    video_rewriter: PromptRewriterGateway | None = None,
    video_rewriters: dict | None = None,
    allowed_origins: tuple[str, ...] = (),
) -> Studio:
    """Wire both model catalogs and one shared model-memory slot."""
    gpu = GpuThread()
    engine_lock = threading.Lock()
    confined = {name: ThreadConfinedBackendGateway(backend, gpu) for name, backend in backends.items()}
    catalog = InMemoryBackendCatalogGateway(confined, default_id=default_id, visible_ids=visible_ids)
    video_catalog = None
    if video_backends:
        selected_video_id = default_video_id or next(iter(video_backends))
        offered_video_ids = visible_video_ids or tuple(video_backends)
        video_catalog = InMemoryVideoBackendCatalogGateway(
            video_backends,
            default_id=selected_video_id,
            visible_ids=offered_video_ids,
        )
    if voice_backend is not None:
        voice_backends = {"auk": voice_backend}
    voice_catalog = None
    if voice_backends:
        voice_catalog = InMemoryVoiceBackendCatalogGateway(
            voice_backends, default_voice_id, visible_voice_ids or tuple(voice_backends)
        )
    if video_rewriters is not None and video_catalog is not None:
        video_rewriter = CatalogPromptRewriter(video_rewriters, video_catalog)
    if video_rewriter is not None:
        video_rewriter = ThreadConfinedPromptRewriter(video_rewriter, gpu)
    runtimes = {**confined, **(video_backends or {}), **(voice_backends or {})}
    residency = InMemoryModelResidencyGateway(runtimes)
    rewriter = ThreadConfinedPromptRewriter(CatalogPromptRewriter(rewriters, catalog), gpu)
    progress = InMemoryProgressGateway(external_cancel=lambda: api.cancellation_requested())
    # The rewrite publishes its own phase, because the page draws that button from
    # it: a rewrite is worth stopping, and only once the model is writing.
    rewrite_progress = InMemoryRewriteProgressGateway(external_cancel=lambda: api.cancellation_requested())
    cancel = CancelRunUseCase(progress, residency)
    video_controller = None
    if video_catalog is not None:
        video_controller = VideoController(
            RunVideoUseCase(video_catalog, progress, engine_lock, residency),
            video_catalog,
            SwitchVideoBackendUseCase(video_catalog, engine_lock, residency),
        )
    controller = FormController(
        describe=DescribeStudioUseCase(catalog, rewriter, video_catalog, video_rewriter),
        run=RunImageUseCase(
            catalog,
            progress,
            InMemoryReferenceStoreGateway(),
            engine_lock=engine_lock,
            rewriter=rewriter,
            residency=residency,
        ),
        read_progress=ReadProgressUseCase(progress),
        cancel=cancel,
        switch=SwitchBackendUseCase(catalog, engine_lock, residency),
        rewrite=RewritePromptUseCase(
            rewriter,
            catalog,
            rewrite_progress,
            video_rewriter=video_rewriter,
            engine_lock=engine_lock,
            residency=residency,
        ),
        read_rewrite_progress=ReadRewriteProgressUseCase(rewrite_progress),
        cancel_rewrite=CancelRewriteUseCase(rewrite_progress),
        release_model=ReleaseModelUseCase(engine_lock, residency),
    )
    presenter = HtmlPresenter(PAGE.read_text(encoding="utf-8"))
    # The JSON API rides on the same controllers: one route map, two transports.
    voice_controller = None
    if voice_catalog is not None:
        backend = voice_catalog.get(voice_catalog.active_id())
        voice_controller = VoiceController(
            RunVoiceUseCase(backend, progress, engine_lock, residency, voice_catalog),
            backend.capabilities(),
            voice_catalog,
            SwitchVoiceBackendUseCase(voice_catalog, engine_lock, residency),
        )
    operations = InMemoryOperationGateway()
    api = JsonApi(
        controller,
        video_controller,
        voice_controller,
        operations=operations,
        completion=CompleteOperationUseCase(operations),
        batches=PrepareBatchUseCase(),
    )
    return Studio(
        handler=make_handler(controller, presenter, video_controller, api, allowed_origins),
        catalog=catalog,
        video_catalog=video_catalog,
        residency=residency,
        cancel=cancel,
        rewriter=rewriter,
        video_rewriter=video_rewriter,
    )
