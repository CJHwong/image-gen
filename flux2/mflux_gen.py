#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mflux==0.18.0",
# ]
# ///
"""
Run the uncensored FLUX.2 klein-base-9B through mflux (Python-MLX).

The `flux2` wrapper runs this script. Text-to-image by default; passing --input
switches to the i2i edit path (mflux-generate-flux2-edit), which conditions on
the same klein-base transformer (no separate edit checkpoint).

The model dir must hold a diffusers-layout klein-base-9b (transformer/,
text_encoder/, vae/, tokenizer/). The uncensored setup symlinks the ponpoke
Qwen3-8B encoder into text_encoder/. Its name must contain "klein-base-9b"
(mflux infers the config from the path). `flux2 help` has the download recipe.

USAGE:
    # text-to-image
    uv run mflux_gen.py --prompt "a red apple" --width 512 --height 512 --output out.png

    # image edit / i2i
    uv run mflux_gen.py --prompt "add a hat" --input ref.png --output out.png --seed 7

    # batch of 4 (seeds increment from --seed, or random without it)
    uv run mflux_gen.py --prompt "a red apple" --count 4 --output apple.png

Model dir defaults to $FLUX2_MFLUX_MODEL_DIR or
~/Library/Caches/models/mflux-klein-base-9b-uncensored.
"""
import argparse
import os
import sys
import time

DEFAULT_MODEL_DIR = os.environ.get(
    "FLUX2_MFLUX_MODEL_DIR",
    os.path.expanduser("~/Library/Caches/models/mflux-klein-base-9b-uncensored"),
)


def resolve_dims(width, height, is_i2i):
    """Omit both -> 256 square (t2i) / source dims (i2i); pass one -> square of
    that; pass both -> as given."""
    if width is None and height is None:
        return (None, None) if is_i2i else (256, 256)
    if width is None:
        width = height
    if height is None:
        height = width
    return width, height


def print_summary(args, width, height, is_i2i):
    """Run header: which weights loaded and with what settings."""
    enc_link = os.path.join(args.model_dir, "text_encoder", "model.safetensors")
    encoder = os.path.realpath(enc_link) if os.path.exists(enc_link) else f"{args.model_dir}/text_encoder"
    if args.seed is None:
        seed = "random"
    elif args.count > 1:
        seed = f"{args.seed}..{args.seed + args.count - 1}"
    else:
        seed = str(args.seed)
    size = "matches input" if (is_i2i and width is None) else f"{width}x{height}"
    rows = [
        ("Engine", "mflux (Python-MLX)"),
        ("Encoder path", encoder),
        ("Transformer", f"{args.model_dir} (int{args.quantize})"),
        ("VAE", os.path.join(args.model_dir, "vae")),
    ]
    if is_i2i:
        rows.append(("Input (i2i)", args.input))
    rows += [
        ("Prompt", args.prompt),
        ("Sampling", f"{args.steps} steps, guidance {args.guidance}"),
        ("Size", size),
        ("Seed", seed),
    ]
    print("\n".join(f"{label:<13}: {value}" for label, value in rows), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Uncensored FLUX.2 klein-base-9B via mflux.")
    parser.add_argument("-p", "--prompt", required=True, help="Prompt to generate.")
    parser.add_argument("--input", help="Reference image for i2i editing. Omit for text-to-image.")
    parser.add_argument("--output", default="uncensored_test.png", help="Output PNG path.")
    parser.add_argument("--width", type=int, help="Image width. Omit both for 256 square (t2i) or the input size (i2i); one alone makes a square.")
    parser.add_argument("--height", type=int, help="Image height.")
    parser.add_argument("--steps", type=int, default=25, help="Denoising steps. Default 25.")
    parser.add_argument("--guidance", type=float, default=4.0, help="CFG guidance. Default 4.0.")
    parser.add_argument("--seed", type=int, help="Seed. Omit for random. With --count, seeds increment.")
    parser.add_argument("--count", type=int, default=1, help="Generate N images in one run.")
    parser.add_argument("-q", "--quantize", type=int, default=8, choices=[3, 4, 5, 6, 8], help="Quantization bits. Default 8.")
    parser.add_argument("--model-dir", default=DEFAULT_MODEL_DIR, help="Local diffusers-layout klein-base-9b dir.")
    args = parser.parse_args()

    is_i2i = args.input is not None
    width, height = resolve_dims(args.width, args.height, is_i2i)

    # mflux appends _seed_<n> itself when a run has multiple seeds, so pass the
    # output path through unchanged.
    argv = [
        "--model", args.model_dir,
        "--prompt", args.prompt,
        "--steps", str(args.steps),
        "--guidance", str(args.guidance),
        "-q", str(args.quantize),
        "--output", args.output,
    ]
    if width is not None:
        argv += ["--width", str(width)]
    if height is not None:
        argv += ["--height", str(height)]
    if args.seed is not None:
        argv += ["--seed"] + [str(args.seed + i) for i in range(args.count)]
    else:
        argv += ["--auto-seeds", str(args.count)]

    if is_i2i:
        argv += ["--image-paths", args.input, "--base-model", "flux2-klein-base-9b"]
        from mflux.models.flux2.cli.flux2_edit_generate import main as mflux_main
    else:
        from mflux.models.flux2.cli.flux2_generate import main as mflux_main

    print_summary(args, width, height, is_i2i)
    sys.argv = ["mflux-flux2"] + argv
    start = time.time()
    mflux_main()
    print(f"{'Timing':<13}: {time.time() - start:.1f}s (includes one-time model load)", flush=True)


if __name__ == "__main__":
    main()
