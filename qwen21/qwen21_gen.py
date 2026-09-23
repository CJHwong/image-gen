#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mflux @ git+https://github.com/mflux-community/mflux@8c00dab2505a96019df9d30bc9c223bf20d733c4",
# ]
# ///
"""
Run Qwen-Image-2.1 through mflux (Python-MLX) on Apple Silicon.

Thin pass-through to mflux's own `mflux-generate-qwen-2.1` parser: every flag it
accepts works here unchanged. This script only injects the defaults this repo
wants (bf16 weights, 40 steps, 1024 square, one auto seed) when you leave them
out, and prints a run header and the wall time; mflux prints the measured peak memory.

Default is bf16, not int8. Measured on an M5 Pro at 1024x1024, 40 steps, six runs:

    peak memory   29.9 to 30.7 GB at BOTH bf16 and -q 8, never higher at bf16
    speed         3.3 s/step cold, 4.3 to 4.6 s/step warm, at BOTH precisions

So quantizing buys nothing here and costs accuracy. Pass `-q 8` when another
process needs the RAM. The 17.5 GB text encoder is never quantized and sets the
floor. Upstream measured ~46 GB at bf16 against ~30.7 GB at -q 8 on an M5 Max;
these runs do not reproduce that gap. One unproven hypothesis: mflux quantizes
in memory after loading bf16, so the peak carries the originals either way.

Resolution is the real speed dial, far more than precision. M5 Pro, bf16, 10
steps, warm cache, one run each:

    size          s/step   10 steps   peak memory   latent tokens
    512 x 512      1.01      10.1s      20.5 GB        1024
    768 x 768      1.79      20.3s      25.1 GB        2304
    1024 x 1024    3.32      41.2s      30.7 GB        4096
    1328 x 1328    6.14      70.8s      39.8 GB        6889

Time tracks the token count almost linearly. The model is trained around 1 MP,
so 1024 stays the default; text rendering is untested at 512. Warm the cache
before trusting a timing: the same 512 run read 30.1s cold and 10.1s warm.

Text in the image renders only when the prompt spells it out. Traditional
Chinese at int8, 1024x1024: a 13-character sign came out 13/13, a dense 41-
character page 37/41, and notes left unspecified came out as fake glyphs. The
errors land on high-stroke characters, not small sizes, so re-roll the seed
rather than enlarging.

The mflux pin is a git commit, not a release: Qwen-Image-2.1 landed in mflux
main on 2026-09-21 (commit 8c00dab, PR #736) and no tagged release carries it
yet. Move the pin to a version once upstream cuts one.

Weights download themselves on first run from Qwen/Qwen-Image-2.1 into the
HuggingFace cache (~33 GB bf16: 14.2 GB transformer, 17.5 GB text encoder,
1.4 GB VAE). The repo is not gated, so no token is needed. Quantization applies
to the transformer and the VAE; the Qwen3-VL text encoder always stays bf16.

USAGE:
    # text-to-image
    uv run qwen21_gen.py --prompt "a red apple" --output apple.png

    # image-to-image
    uv run qwen21_gen.py --prompt "make it winter" --image-path ref.png --output out.png

    # int8 weights, for when something else needs the memory
    uv run qwen21_gen.py --prompt "a red apple" -q 8
"""
import sys
import time

DEFAULT_STEPS = "40"
DEFAULT_SIZE = "1024"
DEFAULT_OUTPUT = "qwen21.png"


def has_flag(argv, *names):
    """True if any of `names` appears in argv, as `--flag` or `--flag=value`."""
    for arg in argv:
        if arg in names or any(arg.startswith(name + "=") for name in names):
            return True
    return False


def drop_quantize(argv):
    """mflux only accepts --quantize 3/4/5/6/8, and reaches bf16 by the flag
    being absent. Let the caller ask for bf16 as `-q 0` and strip it here, so
    one flag spans every precision instead of "pass 8, or pass nothing"."""
    stripped = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg in ("-q", "--quantize"):
            skip_next = True
            continue
        if arg.startswith("-q=") or arg.startswith("--quantize="):
            continue
        stripped.append(arg)
    return stripped


def apply_defaults(argv):
    """Append this repo's defaults for the flags the caller left out. bf16 is
    the default, and mflux spells bf16 as the absent flag, so there is nothing
    to inject: `-q 0` and no flag at all both mean bf16."""
    if flag_value(argv, "-q", "--quantize") == "0":
        argv = drop_quantize(argv)
    if not has_flag(argv, "--steps"):
        argv += ["--steps", DEFAULT_STEPS]
    if not has_flag(argv, "--output"):
        argv += ["--output", DEFAULT_OUTPUT]
    if not has_flag(argv, "--seed", "--auto-seeds"):
        argv += ["--auto-seeds", "1"]
    # Size: mflux resolves dimensions from the reference image on the i2i path,
    # so only default the square when this is text-to-image.
    wants_size = not has_flag(argv, "--width", "--height", "--image", "--image-path")
    if wants_size:
        argv += ["--width", DEFAULT_SIZE, "--height", DEFAULT_SIZE]
    return argv


def flag_value(argv, *names, default=None):
    """Read the value that follows a flag, supporting `--flag=value`."""
    for index, arg in enumerate(argv):
        if arg in names and index + 1 < len(argv):
            return argv[index + 1]
        for name in names:
            if arg.startswith(name + "="):
                return arg.split("=", 1)[1]
    return default


def print_header(argv):
    quantize = flag_value(argv, "-q", "--quantize")
    precision = f"int{quantize}" if quantize else "bf16"
    image_path = flag_value(argv, "--image", "--image-path")
    width = flag_value(argv, "--width")
    height = flag_value(argv, "--height")
    size = f"{width}x{height}" if width and height else "matches input"
    seed = flag_value(argv, "--seed", default="random")
    guidance = flag_value(argv, "--guidance", default="1.0 (guidance-free)")
    rows = [
        ("Engine", "mflux (Python-MLX), Qwen-Image-2.1"),
        ("Weights", "Qwen/Qwen-Image-2.1 (HuggingFace cache)"),
        ("Precision", f"transformer + VAE {precision}, text encoder bf16"),
    ]
    if image_path:
        rows.append(("Input (i2i)", image_path))
    rows += [
        ("Prompt", flag_value(argv, "--prompt", "--prompt-file", default="")),
        ("Sampling", f"{flag_value(argv, '--steps')} steps, guidance {guidance}"),
        ("Size", size),
        ("Seed", seed),
        ("Output", flag_value(argv, "--output")),
    ]
    print("\n".join(f"{label:<11}: {value}" for label, value in rows), flush=True)


def main():
    from mflux.models.qwen21.cli.qwen21_generate import main as mflux_main

    # --help belongs to mflux's parser, which is authoritative for the flag
    # list. Forward it untouched: no injected defaults, no run summary.
    if has_flag(sys.argv[1:], "-h", "--help"):
        sys.argv = ["mflux-generate-qwen-2.1", "--help"]
        mflux_main()
        return

    argv = apply_defaults(sys.argv[1:])
    print_header(argv)
    sys.argv = ["mflux-generate-qwen-2.1"] + argv

    start = time.time()
    try:
        mflux_main()
    finally:
        elapsed = time.time() - start
        # mflux prints its own "Peak MLX memory" line just above this one.
        print(f"{'Timing':<11}: {elapsed:.1f}s (includes model load and any download)", flush=True)


if __name__ == "__main__":
    main()
