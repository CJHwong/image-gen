# krea2-harness

Rust binary that runs Krea 2 on Apple Silicon via [SceneWorks/mlx-gen](https://github.com/SceneWorks/mlx-gen)
(the Rust MLX fork of mflux). Exposes four modes from the `mlx-gen-krea` provider crate:
txt2img, img2img, edit, and pose-control. Native MLX — no Python, no PyTorch, no ComfyUI.

The thin `../krea2` bash wrapper locates this binary and forwards args. Run `../krea2 help`
for the full build + weight-download instructions; this file is the short version.

## Build

```sh
cd krea2/krea2-harness
cargo build --release        # binary -> target/release/krea2
```

Requires Xcode + the Metal toolchain (mlx-rs compiles Metal kernels from source):

```sh
xcode-select -s /Applications/Xcode.app/Contents/Developer
xcodebuild -runFirstLaunch
xcodebuild -downloadComponent MetalToolchain
```

The first build is slow (compiles MLX Metal kernels). Subsequent builds are incremental.

## Weights (one-time, per mode)

Krea 2 ships under the Krea 2 Community License — openly downloadable, not gated.

| Mode | env var | snapshot |
|---|---|---|
| txt2img / img2img | `KREA_TURBO_Q4` | `SceneWorks/krea-2-turbo-mlx` `q4/` (~12.5 GB; use `q8/` ~20.6 GB for near-lossless) |
| edit | `KREA_RAW` + `KREA_EDIT_LORA` | `krea/Krea-2-Raw` + `conradlocke/krea2-identity-edit` LoRA |
| control | `KREA_TURBO_BF16` + `KREA_POSE_OVERLAY` | DENSE `krea/Krea-2-Turbo` bf16 (NOT the packed turnkey) + `SceneWorks/krea2-pose-controlnet-beta` overlay |

```sh
huggingface-cli download SceneWorks/krea-2-turbo-mlx --local-dir ~/models/krea-turbo-q4 --include q4/
export KREA_TURBO_Q4=~/models/krea-turbo-q4/q4
```

`--quant q4|q8` (txt2img/img2img/edit) load-time-quantizes a DENSE snapshot. Do NOT pass it
with a pre-packed turnkey — point `--weights` at the `q4/` or `q8/` dir instead. Control is
dense bf16 only (the engine rejects quant on the pose overlay).

## Use

From the repo root, call the wrapper at `krea2/krea2` (or put it on `PATH`). Run
`krea2/krea2 help` for the full reference; `krea2/krea2 <subcommand> --help` for per-mode flags.

```sh
krea2/krea2 txt2img --prompt "a red fox in a snowy forest" --size 1024x1024 -o /tmp/fox.png
krea2/krea2 img2img --prompt "oil painting" --image photo.jpg --strength 0.5 -o /tmp/oil.png
krea2/krea2 edit    --prompt "change the background to a snowy mountain" --source src.png -o /tmp/ed.png
krea2/krea2 control --prompt "a full-body studio photo" --pose tpose.png --control-scale 0.6 -o /tmp/ctrl.png
```

Override the built binary path with `KREA_BIN` (defaults to
`krea2/krea2-harness/target/release/krea2`).

NOT URL-runnable: this is a compiled Rust binary, not a `uv run` script.
