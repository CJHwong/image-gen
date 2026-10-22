"""Version 1 public contract for separately installed Open Imagine model packages.

Factories and capabilities must be cheap: import engines and load weights only
inside gateway.load/run. Use the media modules for job, result and capability types.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from studio.l1_entities.capabilities import Capabilities as ImageCapabilities
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.voice_capabilities import Capabilities as VoiceCapabilities
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway

API_VERSION = 1


@dataclass(frozen=True)
class PluginContext:
    """Resolved model settings and the host's cancellable subprocess driver."""

    settings: Mapping[str, Any]
    run_process: Callable[..., Any]


@dataclass(frozen=True)
class ModelPlugin:
    """An entry point exports this record, not a loaded model or engine.

    The capability backend_id must equal its entry point name, globally unique
    across Image, Video and Voice. The factory returns that media's gateway.
    A model with no rewriter leaves it unset, so Rewrite is hidden for that model.
    """

    capabilities: ImageCapabilities | VideoCapabilities | VoiceCapabilities
    create: Callable[[PluginContext], ImageBackendGateway | VideoBackendGateway | VoiceBackendGateway]
    rewriter: Callable[[PluginContext], PromptRewriterGateway] | None = None
    api_version: int = API_VERSION


__all__ = ["API_VERSION", "ModelPlugin", "PluginContext", "PromptRewrite", "PromptRewriterGateway"]
