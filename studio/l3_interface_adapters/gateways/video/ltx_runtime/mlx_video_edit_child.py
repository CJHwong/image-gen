"""Run the native video-conditioning pipeline without a task LoRA.

The pipeline accepts an empty LoRA list, while its CLI requires --lora.
This child exposes only the arguments Studio's validated Custom edit needs.
"""

import argparse
import importlib
import random
from typing import Any, cast


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-p", required=True)
    parser.add_argument("-o", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("-H", type=int, required=True)
    parser.add_argument("-W", type=int, required=True)
    parser.add_argument("-f", type=int, required=True)
    parser.add_argument("--frame-rate", type=int, required=True)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--video-conditioning", nargs=2, required=True)
    parser.add_argument("--single-stage", action="store_true")
    parser.add_argument("--stage1-steps", type=int, required=True)
    parser.add_argument("--stage2-steps", type=int, required=True)
    args = parser.parse_args()
    engine = cast(Any, importlib.import_module("ltx_pipelines_mlx.ic_lora"))
    pipeline = engine.ICLoraPipeline(model_dir=args.model, lora_paths=[], low_memory=True)
    pipeline.generate_and_save(
        prompt=args.p,
        output_path=args.o,
        video_conditioning=[(args.video_conditioning[0], float(args.video_conditioning[1]))],
        height=args.H,
        width=args.W,
        num_frames=args.f,
        frame_rate=args.frame_rate,
        seed=args.seed if args.seed is not None else random.randint(0, 2**31 - 1),
        stage1_steps=args.stage1_steps,
        stage2_steps=args.stage2_steps,
        single_stage=args.single_stage,
    )


if __name__ == "__main__":
    main()
