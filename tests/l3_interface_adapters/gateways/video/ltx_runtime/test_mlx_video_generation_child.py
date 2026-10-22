import runpy
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

from studio.l3_interface_adapters.gateways.video.ltx_runtime import mlx_video_generation_child as child


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


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("fails", [False, True])
def test_image_enhancement_reads_first_keyframe_and_frees_before_pipeline(monkeypatch, enabled, fails):
    events = []
    cli = SimpleNamespace()
    args = SimpleNamespace(
        prompt="Move right.",
        images=[SimpleNamespace(path="first.png"), SimpleNamespace(path="last.png")],
        seed=7,
        gemma="same-gemma",
        enhance_prompt=enabled,
    )

    class Vision:
        def load(self, path):
            events.append(("load", path))

        def enhance_i2v(self, prompt, image, seed):
            events.append(("pixels", prompt, image, seed))
            if fails:
                raise ValueError("bad image")
            return "A red shape moves right."

    cli._maybe_enhance_prompt = lambda request: events.append("native") or request.prompt
    cli._guard_enhance_not_gemma4 = lambda path: events.append(("guard", path))
    cli._cmd_a2v = lambda request: None

    def run():
        result = cli._maybe_enhance_prompt(args)
        events.append(("pipeline", result))

    cli.main = run
    modules = {
        "ltx_pipelines_mlx.cli": cli,
        "mlx_image_prompt_enhancement": SimpleNamespace(ImagePromptEnhancer=Vision),
        "ltx_core_mlx.utils.memory": SimpleNamespace(aggressive_cleanup=lambda: events.append("freed")),
    }
    monkeypatch.setattr(child.importlib, "import_module", modules.__getitem__)
    if enabled and fails:
        with pytest.raises(ValueError, match="bad image"):
            child.main()
        assert events[-1] == "freed"
        assert not any(isinstance(item, tuple) and item[0] == "pipeline" for item in events)
    else:
        child.main()
        if enabled:
            assert events == [
                ("guard", "same-gemma"),
                ("load", "same-gemma"),
                ("pixels", "Move right.", "first.png", 7),
                "freed",
                ("pipeline", "A red shape moves right."),
            ]
        else:
            assert events == ["native", ("pipeline", "Move right.")]
