#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "diffusers @ git+https://github.com/huggingface/diffusers@9f1246971270c84dcbe71233edb7a519596a5d02",
#     "torch>=2.4.0",
#     "torchvision",
#     "transformers>=4.57.0",
#     "accelerate",
#     "pillow",
#     "sentencepiece",
# ]
# ///
"""
Qwen-Image-2.1 instruction editing on Apple Silicon, through diffusers on MPS.

This is the EDIT half of the qwen21 backend and it deliberately uses a different
engine from the generate half (mflux, in generator.py). mflux has not ported the Qwen3-VL vision tower, so it
cannot do instruction editing at all. diffusers loads the full
Qwen3VLForConditionalGeneration, vision tower included, which is what turns a
reference image into vision context the transformer can act on.

What that buys, over the mflux img2img:
  - real instruction edits ("remove the sign", "make it night")
  - up to 10 reference images in one call
  - local edits driven by circles or painted annotations on the reference

The cost is bf16 only. There is no int8 path on MPS here, and the vision tower
is resident on top of the 33 GB of weights, so this needs more memory than the
mflux side. Use --offload when it will not fit.

Weights are the same Qwen/Qwen-Image-2.1 repo the mflux path already cached, so
this downloads nothing extra beyond the vision tower shards.

The MPS backend miscomputes the VAE encoder, which crushes the contrast of
every reference image. This script runs that one encode on CPU in fp32 and
keeps the denoise steps on MPS. It is the default, and it costs about 16s per
run. MPS-VAE-ENCODE.md holds the device sweep behind it.

The output can carry alpha. The 2.1 VAE has 4 channels in and out, and asking
an edit to cut the subject out returned alpha spanning 0 to 255: 24% of pixels
near transparent, 71% fully opaque. The references go in as RGBA, so an input's
own alpha reaches the VAE; the pipeline composites it over white for the vision
encoder, which is how the checkpoint was trained.

The diffusers pin is a git commit: QwenImage21Pipeline merged to main on
2026-09-18 (PR #14804) and release 0.40.0 predates it. Move the pin to a version
once upstream cuts one.

USAGE:
    # single-image instruction edit
    uv run qwen21_edit.py --prompt "make it night, lights on" --image room.png --output night.png

    # multiple references (up to 10)
    uv run qwen21_edit.py --prompt "put the cat on the chair" --image cat.png --image chair.png

    # true CFG, for when the edit is being ignored
    uv run qwen21_edit.py --prompt "..." --image a.png --negative-prompt "blurry" --true-cfg-scale 2.5

    # one job from stdin, one PNG back on stdout, nothing on disk
    echo '{"prompt": "...", "images": ["<base64>"]}' | uv run qwen21_edit.py --stdio
"""

import argparse
import base64
import io
import json
import os
import random
import sys
import time

# MPS still lacks a few ops the VL tower reaches for. Falling back to CPU per-op
# is slow but finishes; without this the run dies on the first missing kernel.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

MODEL_REPO = "Qwen/Qwen-Image-2.1"
MAX_REFERENCE_IMAGES = 10


def parse_args():
    parser = argparse.ArgumentParser(description="Qwen-Image-2.1 instruction editing via diffusers on MPS.")
    parser.add_argument("-p", "--prompt", help="The edit instruction.")
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Read one JSON job from stdin and write one JSON result to stdout. See run_stdio.",
    )
    parser.add_argument(
        "--image",
        action="append",
        metavar="PATH",
        help=f"Reference image. Repeat for up to {MAX_REFERENCE_IMAGES} references.",
    )
    parser.add_argument("--output", default="qwen21_edit.png", help="Output PNG path.")
    parser.add_argument("--negative-prompt", help="Enables true CFG; pair with --true-cfg-scale > 1.")
    parser.add_argument("--true-cfg-scale", type=float, default=1.0, help="CFG scale. 2.1 is trained guidance-free.")
    parser.add_argument("--steps", type=int, default=40, help="Denoising steps. Default 40.")
    parser.add_argument("--seed", type=int, help="Seed. Omit for random.")
    parser.add_argument("--output-resolution", type=int, default=1024, help="Target side length. Default 1024.")
    parser.add_argument("--offload", action="store_true", help="Offload each component to CPU when idle.")
    parser.add_argument(
        "--vae-encode-on-mps",
        action="store_true",
        help="Keep the VAE encode on MPS. Diagnostic only: MPS miscomputes it and crushes contrast.",
    )
    parser.add_argument(
        "--no-kv-cache",
        action="store_true",
        help="Disable the text/condition KV cache. Upstream warns it tiles differently in reduced precision.",
    )
    args = parser.parse_args()
    if not args.stdio and not (args.prompt and args.image):
        parser.error("--prompt and --image are required unless --stdio is given")
    return args


def load_references(paths):
    """Read every reference up front so a bad path fails before the model loads."""
    from PIL import Image

    if len(paths) > MAX_REFERENCE_IMAGES:
        sys.exit(f"error: {len(paths)} references given, the model takes at most {MAX_REFERENCE_IMAGES}")
    images = []
    for path in paths:
        if not os.path.exists(path):
            sys.exit(f"error: reference image not found: {path}")
        images.append(Image.open(path).convert("RGBA"))
    return images


def print_header(args, images):
    rows = [
        ("Engine", "diffusers on MPS, Qwen-Image-2.1 edit"),
        ("Weights", f"{MODEL_REPO} (HuggingFace cache)"),
        ("Precision", "bf16 throughout, no quantization on this path"),
        ("References", ", ".join(f"{p} ({im.size[0]}x{im.size[1]})" for p, im in zip(args.image, images, strict=True))),
        ("Prompt", args.prompt),
        ("Sampling", f"{args.steps} steps, true CFG {args.true_cfg_scale}"),
        ("KV cache", "off" if args.no_kv_cache else "on"),
        ("VAE encode", "mps (known broken)" if args.vae_encode_on_mps else "cpu fp32"),
        ("Resolution", str(args.output_resolution)),
        ("Seed", "random" if args.seed is None else str(args.seed)),
        ("Output", args.output),
    ]
    print("\n".join(f"{label:<12}: {value}" for label, value in rows), flush=True)


def _encode_vae_on_cpu(pipe):
    """Run the VAE encode on CPU. Everything else stays on MPS.

    The MPS backend miscomputes the Qwen-Image-2.1 VAE encoder: contrast drops
    from 64.2 to 17.8 at both bf16 and fp32, while CPU fp32 reproduces the
    source. So it is a device bug, not a precision one. Text-to-image never hits
    it because that path only decodes. MPS-VAE-ENCODE.md has the full sweep.

    Encode runs once per reference image, so the CPU detour costs seconds while
    the 40 denoise steps stay on the GPU.
    """
    import torch

    encode_on_pipeline_device = pipe._encode_vae_image

    def encode_on_cpu(image, generator):
        device, dtype = pipe.vae.device, pipe.vae.dtype
        pipe.vae.to("cpu", torch.float32)
        try:
            latents = encode_on_pipeline_device(image.to("cpu", torch.float32), generator)
        finally:
            pipe.vae.to(device, dtype)
        return latents.to(device, torch.bfloat16)

    pipe._encode_vae_image = encode_on_cpu


def build_pipeline(offload, encode_on_mps):
    import torch
    from diffusers import QwenImage21Pipeline

    if not torch.backends.mps.is_available():
        sys.exit("error: no MPS device. This script targets Apple Silicon.")

    pipe = QwenImage21Pipeline.from_pretrained(MODEL_REPO, torch_dtype=torch.bfloat16)
    if not encode_on_mps:
        _encode_vae_on_cpu(pipe)
    if offload:
        pipe.enable_model_cpu_offload(device="mps")
    else:
        pipe.to("mps")
    return pipe


def run_edit(pipe, job, log, on_step=None):
    """Produce one edited image from an already built pipeline.

    Both entry points come through here, so the CLI and the server cannot drift.
    `job` is a plain dict rather than an argparse namespace because the stdio
    path receives one over a pipe. `log` takes the progress lines, which go to
    stdout for the CLI and to stderr for the server.

    The pipeline is a parameter rather than something built here, because the
    server feeds this many jobs over one process. Loading it costs 20 to 36
    seconds and there is no reason to pay that per edit.

    Returns the image, the seed it actually used, and the wall-clock seconds.
    """
    import torch

    start = time.time()
    seed = job["seed"] if job["seed"] is not None else random.randint(0, 1_000_000_000)
    # A CPU generator keeps the seed reproducible; diffusers moves the noise to
    # the pipeline's device itself.
    generator = torch.Generator("cpu").manual_seed(seed)

    callback = None
    if on_step is not None:

        def callback(_pipe, index, _timestep, tensors):
            on_step(index + 1, job["steps"])
            return tensors

    result = pipe(
        prompt=job["prompt"],
        image=job["images"],
        negative_prompt=job["negative_prompt"],
        true_cfg_scale=job["true_cfg_scale"],
        num_inference_steps=job["steps"],
        output_resolution=job["output_resolution"],
        use_kv_cache=job["use_kv_cache"],
        generator=generator,
        callback_on_step_end=callback,
    )
    elapsed = time.time() - start
    peak = torch.mps.driver_allocated_memory() / 1024**3
    log(f"{'Timing':<12}: {elapsed:.1f}s total")
    log(f"{'MPS memory':<12}: {peak:.1f} GiB allocated at exit")
    return result.images[0], seed, elapsed


def job_from_args(args, images):
    return {
        "prompt": args.prompt,
        "images": images,
        "negative_prompt": args.negative_prompt,
        "true_cfg_scale": args.true_cfg_scale,
        "steps": args.steps,
        "output_resolution": args.output_resolution,
        "use_kv_cache": not args.no_kv_cache,
        "seed": args.seed,
    }


def parse_stdio_job(request):
    """Turn one decoded request into the dict run_edit wants."""
    from PIL import Image

    encoded = request.get("images") or []
    if not encoded:
        raise ValueError("the job carried no reference image")
    if len(encoded) > MAX_REFERENCE_IMAGES:
        raise ValueError(f"{len(encoded)} references given, the model takes at most {MAX_REFERENCE_IMAGES}")
    return {
        "prompt": request["prompt"],
        "images": [Image.open(io.BytesIO(base64.b64decode(b))).convert("RGBA") for b in encoded],
        "negative_prompt": request.get("negative_prompt") or None,
        "true_cfg_scale": float(request.get("true_cfg_scale") or 1.0),
        "steps": int(request.get("steps") or 40),
        "output_resolution": int(request.get("output_resolution") or 1024),
        "use_kv_cache": bool(request.get("use_kv_cache", True)),
        "seed": request.get("seed"),
    }


def run_stdio(args):
    """JSON jobs in on stdin, JSON results out on stdout, one per line.

    This exists for the studio web server: edit.py runs it as a child. The server cannot use the flag interface
    for two reasons. Reference images would have to be written to disk to be
    passed as paths, and the page's whole point is that nothing reaches disk.
    The prompt would sit in the process arguments, where any `ps` shows it.

    A pipe solves both. Images arrive as base64 PNG and leave the same way.
    Progress lines go to stderr as "step N/M" so the caller can report them;
    stdout carries one JSON result per job and nothing else.

    This loops until stdin closes, and builds the pipeline once, from the
    --offload and --vae-encode-on-mps flags of this process. Loading it
    costs 20 to 36 seconds, so a caller sending several edits pays that once
    instead of once per edit. A single job followed by EOF still works, which
    is what a plain `echo ... | qwen21_edit.py --stdio` does.

    Line framing is safe here: json.dumps escapes every newline inside a string
    and base64 carries none, so one message is always one line.
    """

    def log(line):
        print(line, file=sys.stderr, flush=True)

    def on_step(step, total):
        print(f"step {step}/{total}", file=sys.stderr, flush=True)

    pipe = None
    for line in sys.stdin.buffer:
        line = line.strip()
        if not line:
            continue
        try:
            job = parse_stdio_job(json.loads(line))
        except (ValueError, KeyError) as error:
            json.dump({"error": str(error)}, sys.stdout)
            print(flush=True)
            continue

        if pipe is None:
            start = time.time()
            pipe = build_pipeline(args.offload, args.vae_encode_on_mps)
            log(f"{'Loaded':<12}: {time.time() - start:.1f}s")
        else:
            log("ready")

        try:
            image, seed, elapsed = run_edit(pipe, job, log, on_step)
        except Exception as error:
            json.dump({"error": f"{type(error).__name__}: {error}"}, sys.stdout)
            print(flush=True)
            continue

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        json.dump(
            {
                "image": base64.b64encode(buffer.getvalue()).decode("ascii"),
                "seed": seed,
                "seconds": round(elapsed, 1),
                "width": image.width,
                "height": image.height,
            },
            sys.stdout,
        )
        print(flush=True)


def main():
    args = parse_args()
    if args.stdio:
        run_stdio(args)
        return

    images = load_references(args.image)
    print_header(args, images)
    log = lambda line: print(line, flush=True)  # noqa: E731
    start = time.time()
    pipe = build_pipeline(args.offload, args.vae_encode_on_mps)
    log(f"{'Loaded':<12}: {time.time() - start:.1f}s")
    image, seed, _ = run_edit(pipe, job_from_args(args, images), log)
    image.save(args.output)
    print(f"{'Seed used':<12}: {seed}", flush=True)


if __name__ == "__main__":
    main()
