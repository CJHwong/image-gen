import runpy
import sys
from types import SimpleNamespace

import pytest

from studio.l3_interface_adapters.gateways.video.ltx_runtime import mlx_layout_to_render_child as child


@pytest.mark.parametrize("entrypoint", [False, True])
def test_layout_recipe_keeps_virtual_look_time_samples_both_stages_and_loads_real_weights(
    tmp_path, monkeypatch, entrypoint
):
    events = []

    class Pipeline:
        model_dir = tmp_path
        upsampler = None

        def load(self):
            events.append("original load")

    class Upsampler:
        def __init__(self, path, name):
            assert path == tmp_path
            assert name == "spatial_upscaler_x2_v1_0"

        def load(self):
            events.append("weights loaded")
            return "trained upscaler"

    engine = SimpleNamespace(ICLoraPipeline=Pipeline)
    frame_args = SimpleNamespace(resolve_frame_indices=lambda images, frames: [SimpleNamespace(frame_idx=frames - 1)])
    sampler = SimpleNamespace(euler_ancestral_denoising_loop=lambda *a, **kw: events.append(kw["noise_seed"]))
    modules = {
        "ltx_pipelines_mlx.ic_lora": engine,
        "ltx_pipelines_mlx.utils.args": frame_args,
        "ltx_pipelines_mlx.utils.blocks": SimpleNamespace(VideoUpsampler=Upsampler),
        "ltx_pipelines_mlx.utils.samplers": sampler,
        "ltx_core_mlx.components.diffusion_steps": SimpleNamespace(EulerAncestralDiffusionStep=lambda: None),
        "ltx_pipelines_mlx.cli": SimpleNamespace(main=lambda: events.append("cli")),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, "argv", [child.__file__, "ic-lora", "--seed", "7"])
    if entrypoint:
        runpy.run_path(child.__file__, run_name="__main__")
    else:
        child.main()
    look = SimpleNamespace(frame_idx=-1)
    resolved = frame_args.resolve_frame_indices([look, SimpleNamespace(frame_idx=-2)], 49)
    assert resolved[0] is look and resolved[1].frame_idx == 48
    engine.denoise_loop(model=None, video_state=None, audio_state=None, sigmas=[])
    engine.denoise_loop(model=None, video_state=None, audio_state=None, sigmas=[])
    pipeline = Pipeline()
    with pytest.raises(FileNotFoundError, match=r"requires the LTX-2\.5 upscaler"):
        pipeline.load()
    (tmp_path / "spatial_upscaler_x2_v1_0.safetensors").touch()
    with pytest.raises(FileNotFoundError, match=r"_config\.json"):
        pipeline.load()
    (tmp_path / "spatial_upscaler_x2_v1_0_config.json").touch()
    pipeline.load()
    pipeline.load()
    assert pipeline.upsampler == "trained upscaler"
    assert events == ["cli", 7, 9, "weights loaded", "original load", "original load"]
