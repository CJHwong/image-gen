"""Installed-package discovery and validation at the composition boundary."""

import re
from collections.abc import Mapping
from importlib import metadata
from types import MappingProxyType

from studio.l1_entities.capabilities import Capabilities as ImageCapabilities
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.voice_capabilities import Capabilities as VoiceCapabilities
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway
from studio.l3_interface_adapters.gateways.audio.stub_voice_backend_gateway import StubVoiceBackendGateway
from studio.l3_interface_adapters.gateways.image.stub_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.prompt_rewriters import NoPromptRewriter, StubPromptRewriter
from studio.l3_interface_adapters.gateways.video.stub_video_backend_gateway import StubVideoBackendGateway
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner
from studio.plugins import API_VERSION, ModelPlugin, PluginContext

GROUPS = {
    "image": "open_imagine.models.image",
    "video": "open_imagine.models.video",
    "voice": "open_imagine.models.audio",
}
CAPABILITIES = {"image": ImageCapabilities, "video": VideoCapabilities, "voice": VoiceCapabilities}
GATEWAYS = {"image": ImageBackendGateway, "video": VideoBackendGateway, "voice": VoiceBackendGateway}


class ModelPlugins:
    """Read metadata eagerly, import only explicitly visible models, never load weights."""

    def __init__(self, reserved: Mapping[str, Mapping]):
        self.entries = {kind: {} for kind in GROUPS}
        self.loaded = {}
        occupied = {name for registry in reserved.values() for name in registry}
        for kind, group in GROUPS.items():
            for entry in sorted(metadata.entry_points(group=group), key=lambda item: item.name):
                if not re.fullmatch(r"[a-z][a-z0-9_]*", entry.name):
                    raise ConfigError(f"Plugin id {entry.name!r} must use lowercase letters, digits and underscores.")
                if entry.name in occupied:
                    raise ConfigError(
                        f"Duplicate model id {entry.name!r} from {group}; plugin ids cannot replace another model."
                    )
                occupied.add(entry.name)
                self.entries[kind][entry.name] = entry

    def ids(self, kind: str) -> tuple[str, ...]:
        return tuple(self.entries[kind])

    def declaration(self, kind: str, name: str) -> ModelPlugin:
        if name not in self.loaded:
            entry = self.entries[kind][name]
            try:
                plugin = entry.load()
                if not isinstance(plugin, ModelPlugin) or plugin.api_version != API_VERSION:
                    raise ValueError(f"expected ModelPlugin API version {API_VERSION}")
                if not isinstance(plugin.capabilities, CAPABILITIES[kind]) or plugin.capabilities.backend_id != name:
                    raise ValueError(f"expected {kind} capabilities with backend_id {name!r}")
                if not callable(plugin.create) or (plugin.rewriter is not None and not callable(plugin.rewriter)):
                    raise ValueError("create and optional rewriter must be factories")
                self.loaded[name] = plugin
            except Exception as error:
                raise ConfigError(f"Cannot load model plugin {entry.group}/{name}: {error}") from error
        return self.loaded[name]

    def context(self, config: Config, name: str) -> PluginContext:
        return PluginContext(MappingProxyType(config.backend(name)), SubprocessRunner().execute)

    def build(self, kind: str, name: str, config: Config, stub: bool = False, **_):
        plugin = self.declaration(kind, name)
        if stub:
            capabilities = plugin.capabilities
            if isinstance(capabilities, ImageCapabilities):
                return StubBackendGateway(capabilities)
            if isinstance(capabilities, VideoCapabilities):
                return StubVideoBackendGateway(capabilities)
            return StubVoiceBackendGateway(capabilities=capabilities)
        try:
            gateway = plugin.create(self.context(config, name))
            if not isinstance(gateway, GATEWAYS[kind]) or gateway.capabilities() != plugin.capabilities:
                raise ValueError("factory must return its media gateway with the declared capabilities")
            return gateway
        except Exception as error:
            raise ConfigError(f"Cannot construct {kind} model plugin {name}: {error}") from error

    def rewriter(self, kind: str, name: str, config: Config, stub: bool = False) -> PromptRewriterGateway:
        factory = self.declaration(kind, name).rewriter
        if factory is None:
            return NoPromptRewriter()
        if stub:
            return StubPromptRewriter()
        try:
            rewriter = factory(self.context(config, name))
            if not isinstance(rewriter, PromptRewriterGateway):
                raise ValueError("rewriter must return a PromptRewriterGateway")
            return rewriter
        except Exception as error:
            raise ConfigError(f"Cannot construct {kind} rewriter plugin {name}: {error}") from error
