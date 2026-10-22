from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l1_entities.voice_capabilities import Capabilities as VoiceCapabilities
from studio.l1_entities.voice_capabilities import ModeSpec as VoiceMode
from studio.l3_interface_adapters.gateways.audio.stub_voice_backend_gateway import StubVoiceBackendGateway
from studio.l3_interface_adapters.gateways.image.stub_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.prompt_rewriters import NoPromptRewriter, StubPromptRewriter
from studio.l3_interface_adapters.gateways.video.stub_video_backend_gateway import StubVideoBackendGateway
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.model_plugins import GROUPS, ModelPlugins
from studio.plugins import ModelPlugin
from tests.support.fakes import fake_capabilities, fake_video_capabilities


def configuration():
    return Config(
        "example_image",
        ("example_image",),
        "example_video",
        ("example_video",),
        {"example_image": {"key": "value"}},
        "example_voice",
        ("example_voice",),
    )


def declarations():
    image = fake_capabilities("example_image")
    video = fake_video_capabilities("example_video")
    voice = VoiceCapabilities("example_voice", "Voice", "", (VoiceMode("design", "Generate", ()),), 16)
    return {
        "image": ModelPlugin(image, lambda context: StubBackendGateway(image)),
        "video": ModelPlugin(video, lambda context: StubVideoBackendGateway(video)),
        "voice": ModelPlugin(voice, lambda context: StubVoiceBackendGateway(capabilities=voice)),
    }


def installed(monkeypatch, plugins=None, entries=None):
    plugins = declarations() if plugins is None else plugins
    entries = (
        entries
        if entries is not None
        else [
            SimpleNamespace(name=plugin.capabilities.backend_id, group=GROUPS[kind], load=Mock(return_value=plugin))
            for kind, plugin in plugins.items()
        ]
    )
    monkeypatch.setattr(
        "studio.l4_frameworks_and_drivers.model_plugins.metadata.entry_points",
        lambda group: [entry for entry in entries if entry.group == group],
    )
    return ModelPlugins({}), entries


def test_discovery_does_not_import_models_and_selected_declarations_are_cached(monkeypatch):
    registry, entries = installed(monkeypatch)
    assert registry.ids("image") == ("example_image",)
    assert all(not entry.load.called for entry in entries)
    assert registry.declaration("image", "example_image") is registry.declaration("image", "example_image")
    entries[0].load.assert_called_once()
    assert not entries[1].load.called


@pytest.mark.parametrize("name", ["Upper", "with-dash", "1model", "bad/path"])
def test_ids_are_safe_and_consistent_with_existing_backend_configuration(monkeypatch, name):
    with pytest.raises(ConfigError, match="Plugin id"):
        installed(monkeypatch, entries=[SimpleNamespace(name=name, group=GROUPS["image"])])


def test_duplicate_ids_cannot_shadow_builtins_or_other_media(monkeypatch):
    entries = [SimpleNamespace(name="same", group=GROUPS[kind]) for kind in ("image", "video")]
    with pytest.raises(ConfigError, match="Duplicate model id"):
        installed(monkeypatch, entries=entries)
    installed(monkeypatch, entries=entries[:1])
    with pytest.raises(ConfigError, match="Duplicate model id"):
        ModelPlugins({"image": {"same": object()}})


@pytest.mark.parametrize(
    "bad",
    [
        object(),
        replace(declarations()["image"], api_version=2),
        replace(declarations()["image"], capabilities=fake_capabilities("different")),
        replace(declarations()["image"], capabilities=declarations()["voice"].capabilities),
        replace(declarations()["image"], create=None),
        replace(declarations()["image"], rewriter=3),
    ],
)
def test_selected_invalid_declarations_have_actionable_errors(monkeypatch, bad):
    registry, _ = installed(
        monkeypatch, entries=[SimpleNamespace(name="example_image", group=GROUPS["image"], load=lambda: bad)]
    )
    with pytest.raises(ConfigError, match=r"Cannot load model plugin open_imagine.models.image/example_image"):
        registry.declaration("image", "example_image")


def test_import_failure_names_the_plugin(monkeypatch):
    entry = SimpleNamespace(name="broken", group=GROUPS["image"], load=Mock(side_effect=ImportError("missing extra")))
    registry, _ = installed(monkeypatch, entries=[entry])
    with pytest.raises(ConfigError, match="missing extra"):
        registry.declaration("image", "broken")


@pytest.mark.parametrize("kind", ["image", "video", "voice"])
@pytest.mark.parametrize("stub", [False, True])
def test_each_media_uses_its_boundary_and_stub_never_constructs_the_engine(monkeypatch, kind, stub):
    plugins = declarations()
    original = plugins[kind]
    factory = Mock(side_effect=original.create)
    plugins[kind] = replace(original, create=factory)
    registry, _ = installed(monkeypatch, plugins)
    gateway = registry.build(kind, original.capabilities.backend_id, configuration(), stub)
    assert gateway.capabilities() == original.capabilities
    assert factory.call_count == (0 if stub else 1)


def test_context_has_resolved_settings_and_cancellable_host_process_driver(monkeypatch):
    registry, _ = installed(monkeypatch)
    context = registry.context(configuration(), "example_image")
    assert context.settings == {"key": "value"} and callable(context.run_process)
    with pytest.raises(TypeError):
        context.settings["key"] = "changed"


@pytest.mark.parametrize(
    "factory",
    [
        lambda context: object(),
        lambda context: StubBackendGateway(fake_capabilities("wrong")),
        Mock(side_effect=RuntimeError("failed factory")),
    ],
)
def test_factory_errors_and_capability_mismatches_are_rejected(monkeypatch, factory):
    registry, _ = installed(monkeypatch, {"image": replace(declarations()["image"], create=factory)})
    with pytest.raises(ConfigError, match="Cannot construct image model plugin"):
        registry.build("image", "example_image", configuration())


def test_rewriters_are_optional_typed_lazy_and_stubbed(monkeypatch):
    registry, _ = installed(monkeypatch)
    assert isinstance(registry.rewriter("image", "example_image", configuration()), NoPromptRewriter)
    factory = Mock(return_value=NoPromptRewriter())
    registry, _ = installed(monkeypatch, {"image": replace(declarations()["image"], rewriter=factory)})
    assert isinstance(registry.rewriter("image", "example_image", configuration(), True), StubPromptRewriter)
    factory.assert_not_called()
    assert isinstance(registry.rewriter("image", "example_image", configuration()), NoPromptRewriter)
    factory.return_value = object()
    with pytest.raises(ConfigError, match="rewriter must return"):
        registry.rewriter("image", "example_image", configuration())
    factory.side_effect = RuntimeError("rewrite failed")
    with pytest.raises(ConfigError, match="rewrite failed"):
        registry.rewriter("image", "example_image", configuration())


def test_public_media_sdk_imports_the_host_contracts():
    from studio.plugins import audio, image, video

    assert (
        image.ImageBackendGateway
        is __import__(
            "studio.l2_use_cases.boundaries.image_backend_gateway", fromlist=["ImageBackendGateway"]
        ).ImageBackendGateway
    )
    assert (
        video.VideoBackendGateway
        is __import__(
            "studio.l2_use_cases.boundaries.video_backend_gateway", fromlist=["VideoBackendGateway"]
        ).VideoBackendGateway
    )
    assert audio.Capabilities is VoiceCapabilities


def test_composition_builds_all_three_external_models_without_platform_or_engine_loading(monkeypatch):
    from studio.l4_frameworks_and_drivers import main

    registry, _ = installed(monkeypatch)
    monkeypatch.setattr(
        main, "require_mlx", Mock(side_effect=AssertionError("plugin-only composition must not impose MLX"))
    )
    studio = main.create_studio(configuration(), plugins=registry)
    try:
        assert studio.video_catalog is not None and studio.video_rewriter is not None
        assert studio.active_capabilities().backend_id == "example_image"
        assert studio.video_catalog.active_id() == "example_video"
        assert studio.video_rewriter.modes() == ()
    finally:
        studio.shutdown()


def test_stub_composition_preserves_plugin_capabilities_and_rewrite_absence(monkeypatch):
    from studio.l4_frameworks_and_drivers import main

    registry, _ = installed(monkeypatch)
    studio = main.create_studio(configuration(), stub=True, plugins=registry)
    try:
        assert studio.video_catalog is not None and studio.video_rewriter is not None
        assert studio.active_capabilities().backend_id == "example_image"
        assert studio.rewriter is not None and studio.video_rewriter is not None
        assert studio.rewriter.modes() == ()
        assert studio.video_rewriter.modes() == ()
    finally:
        studio.shutdown()


def test_image_plugin_rewriter_follows_the_selected_backend(monkeypatch):
    from studio.l4_frameworks_and_drivers.main import build_rewriters

    registry, _ = installed(
        monkeypatch, {"image": replace(declarations()["image"], rewriter=lambda context: StubPromptRewriter())}
    )
    assert build_rewriters(configuration(), registry)["example_image"].modes() == ("generate", "edit")


def test_video_rewrite_switches_between_plugin_and_builtin_without_cross_model_enhancement(monkeypatch):
    from studio.l4_frameworks_and_drivers import main

    registry, _ = installed(monkeypatch)
    config = replace(configuration(), visible_video_backends=("example_video", "ltx25_mlx"))
    studio = main.create_studio(config, stub=True, plugins=registry)
    try:
        assert studio.video_rewriter is not None and studio.video_catalog is not None
        assert studio.video_rewriter.modes() == ()
        studio.video_catalog.set_active("ltx25_mlx")
        assert studio.video_rewriter.modes() == ("generate", "edit")
        studio.video_catalog.set_active("example_video")
        assert studio.video_rewriter.modes() == ()
    finally:
        studio.shutdown()


def test_video_plugin_rewrite_and_release_share_the_model_thread(monkeypatch):
    import threading

    from studio.l4_frameworks_and_drivers import main

    calls = []

    class Rewriter(StubPromptRewriter):
        def rewrite(self, prompt, mode, references, on_writing, should_stop):
            calls.append(threading.get_ident())
            return super().rewrite(prompt, mode, references, on_writing, should_stop)

        def release(self):
            calls.append(threading.get_ident())

    registry, _ = installed(
        monkeypatch, {**declarations(), "video": replace(declarations()["video"], rewriter=lambda context: Rewriter())}
    )
    studio = main.create_studio(configuration(), plugins=registry)
    assert studio.video_rewriter is not None
    studio.video_rewriter.rewrite("A landscape", "generate", (), lambda: None, lambda: False)
    studio.shutdown()
    assert len(calls) == 2
    assert calls[0] == calls[1] != threading.get_ident()


def test_example_video_reports_encoder_failure_instead_of_callback_type_error(monkeypatch, tmp_path):
    from pathlib import Path

    from studio.l1_entities.errors import StudioError
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner
    from studio.plugins import PluginContext
    from studio.plugins.video import VideoJob

    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "examples/model_plugin"))
    from importlib import import_module

    video = import_module("open_imagine_example.video")

    encoder = tmp_path / "ffmpeg"
    encoder.write_text("#!/bin/sh\necho 'fixture encoder error' >&2\nexit 7\n")
    encoder.chmod(0o755)
    monkeypatch.setattr(video.shutil, "which", lambda name: str(encoder))
    gateway = video.ExampleVideoGateway(PluginContext({}, SubprocessRunner().execute))
    with pytest.raises(StudioError, match=r"Example Video failed \(7\): fixture encoder error"):
        gateway.run(VideoJob("test", 256, 256, 17, 8, 7))
