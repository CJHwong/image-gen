import runpy
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

from studio.l4_frameworks_and_drivers import mlx_video_generation_child as child


@pytest.mark.parametrize("entrypoint", [False, True])
def test_native_audio_enhancement_runs_once_before_pipeline_loading(monkeypatch, entrypoint):
    events = []
    cli = cast(Any, ModuleType("ltx_pipelines_mlx.cli"))
    args = SimpleNamespace(prompt="A singer.", seed=7, audio="reference.wav", gemma="gemma-3")

    def enhance(request):
        events.append(("enhance", request.prompt, request.seed, request.audio, request.enhance_prompt))
        return "A detailed singer performance."

    def audio(request):
        events.append(("generate", request.prompt, request.audio))

    cli._maybe_enhance_prompt = enhance
    cli._cmd_a2v = audio
    cli.main = lambda: cli._cmd_a2v(args)
    monkeypatch.setitem(sys.modules, "ltx_pipelines_mlx.cli", cli)
    if entrypoint:
        runpy.run_path(child.__file__, run_name="__main__")
    else:
        child.main()
    assert events == [
        ("enhance", "A singer.", 7, "reference.wav", True),
        ("generate", "A detailed singer performance.", "reference.wav"),
    ]
