"""Adapt the pinned MLX IC-LoRA pipeline to the Layout to Render recipe.

Keep the look image at virtual time -1, use ancestral sampling in both stages,
and require the LTX-2.5 upscaler weights rather than the port's random fallback.
"""

import argparse
import importlib
from typing import Any, cast


def configure(engine, frame_args, blocks, samplers, steps, seed):
    original_resolve = frame_args.resolve_frame_indices

    def resolve(images, frames):
        return [image if image.frame_idx == -1 else original_resolve([image], frames)[0] for image in images]

    frame_args.resolve_frame_indices = resolve
    stage = 0

    def ancestral(*, model, video_state, audio_state, sigmas, **kwargs):
        nonlocal stage
        noise_seed = seed + stage * 2
        stage += 1
        return samplers.euler_ancestral_denoising_loop(
            sigmas,
            video_state,
            audio_state,
            steps.EulerAncestralDiffusionStep(),
            model,
            noise_seed=noise_seed,
            **kwargs,
        )

    engine.denoise_loop = ancestral
    original_load = engine.ICLoraPipeline.load

    def load(self):
        if self.upsampler is None:
            name = "spatial_upscaler_x2_v1_0"
            for suffix in (".safetensors", "_config.json"):
                path = self.model_dir / (name + suffix)
                if not path.is_file():
                    raise FileNotFoundError(f"Layout to Render requires the LTX-2.5 upscaler: {path}")
            self.upsampler = blocks.VideoUpsampler(self.model_dir, name=name).load()
        return original_load(self)

    engine.ICLoraPipeline.load = load


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--seed", type=int, default=0)
    args, _ = parser.parse_known_args()
    modules = [
        cast(Any, importlib.import_module(name))
        for name in (
            "ltx_pipelines_mlx.ic_lora",
            "ltx_pipelines_mlx.utils.args",
            "ltx_pipelines_mlx.utils.blocks",
            "ltx_pipelines_mlx.utils.samplers",
            "ltx_core_mlx.components.diffusion_steps",
        )
    ]
    configure(modules[0], modules[1], modules[2], modules[3], modules[4], args.seed)
    cast(Any, importlib.import_module("ltx_pipelines_mlx.cli")).main()


if __name__ == "__main__":
    main()
