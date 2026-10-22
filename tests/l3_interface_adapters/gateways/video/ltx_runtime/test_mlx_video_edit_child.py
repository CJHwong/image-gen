import runpy
import sys
from types import SimpleNamespace

import pytest

from studio.l3_interface_adapters.gateways.video.ltx_runtime import mlx_video_edit_child as child


@pytest.mark.parametrize("entrypoint", [False, True])
@pytest.mark.parametrize("seed", [None, 7])
def test_custom_edit_passes_the_clip_and_prompt_without_loading_any_lora(monkeypatch, entrypoint, seed):
    events = []

    class Pipeline:
        def __init__(self, **kwargs):
            events.append(("load", kwargs))

        def generate_and_save(self, **kwargs):
            events.append(("render", kwargs))

    monkeypatch.setitem(sys.modules, "ltx_pipelines_mlx.ic_lora", SimpleNamespace(ICLoraPipeline=Pipeline))
    monkeypatch.setattr(child.random, "randint", lambda start, end: 42)
    args = [
        child.__file__,
        "-p",
        "Change the mug to blue",
        "-o",
        "result.mp4",
        "--model",
        "pack",
        "-H",
        "384",
        "-W",
        "640",
        "-f",
        "49",
        "--frame-rate",
        "24",
        "--video-conditioning",
        "clip.mp4",
        "1.0",
        "--single-stage",
        "--stage1-steps",
        "8",
        "--stage2-steps",
        "0",
    ]
    if seed is not None:
        args.extend(("--seed", str(seed)))
    monkeypatch.setattr(sys, "argv", args)
    if entrypoint:
        runpy.run_path(child.__file__, run_name="__main__")
    else:
        child.main()

    assert events == [
        ("load", {"model_dir": "pack", "lora_paths": [], "low_memory": True}),
        (
            "render",
            {
                "prompt": "Change the mug to blue",
                "output_path": "result.mp4",
                "video_conditioning": [("clip.mp4", 1.0)],
                "height": 384,
                "width": 640,
                "num_frames": 49,
                "frame_rate": 24,
                "seed": seed if seed is not None else 42,
                "stage1_steps": 8,
                "stage2_steps": 0,
                "single_stage": True,
            },
        ),
    ]
