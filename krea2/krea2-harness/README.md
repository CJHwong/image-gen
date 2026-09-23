# krea2-harness

Rust binary that runs Krea 2 on Apple Silicon via [SceneWorks/mlx-gen](https://github.com/SceneWorks/mlx-gen)
(the Rust MLX fork of mflux). Exposes four modes from the `mlx-gen-krea` provider crate:
txt2img, img2img, edit, and pose-control. Native MLX — no Python, no PyTorch, no ComfyUI.

The thin `../krea2` bash wrapper locates this binary and forwards args. This file is the
reference for build and weights; `../krea2 help` lists the env vars and subcommands.

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
# txt2img / img2img (q4; swap q4 for q8 for near-lossless, ~20.6 GB, wants 48 GB)
huggingface-cli download SceneWorks/krea-2-turbo-mlx --local-dir ~/models/krea-turbo-q4 --include q4/
export KREA_TURBO_Q4=~/models/krea-turbo-q4/q4

# edit (confirm the exact LoRA filename inside that repo before exporting)
huggingface-cli download krea/Krea-2-Raw --local-dir ~/models/krea-raw
huggingface-cli download conradlocke/krea2-identity-edit --local-dir ~/models/krea-edit-lora
export KREA_RAW=~/models/krea-raw
export KREA_EDIT_LORA=~/models/krea-edit-lora/krea2_identity_edit_v1_1_r128.safetensors

# control
huggingface-cli download krea/Krea-2-Turbo --local-dir ~/models/krea-turbo-bf16
huggingface-cli download SceneWorks/krea2-pose-controlnet-beta --local-dir ~/models/krea-pose
export KREA_TURBO_BF16=~/models/krea-turbo-bf16
export KREA_POSE_OVERLAY=~/models/krea-pose/control_step5000.safetensors
```

`--quant q4|q8` (txt2img/img2img/edit) load-time-quantizes a DENSE snapshot. Do NOT pass it
with a pre-packed turnkey — point `--weights` at the `q4/` or `q8/` dir instead. Control is
dense bf16 only (the engine rejects quant on the pose overlay).

## Use

From the repo root, call the wrapper at `krea2/krea2` (or put it on `PATH`). Run
`krea2/krea2 <subcommand> --help` for per-mode flags.

```sh
krea2/krea2 txt2img --prompt "a red fox in a snowy forest" --size 1024x1024 -o /tmp/fox.png
krea2/krea2 img2img --prompt "oil painting" --image photo.jpg --strength 0.5 -o /tmp/oil.png
krea2/krea2 edit    --prompt "change the background to a snowy mountain" --source src.png -o /tmp/ed.png
krea2/krea2 control --prompt "a full-body studio photo" --pose tpose.png --control-scale 0.6 -o /tmp/ctrl.png
```

Override the built binary path with `KREA_BIN` (defaults to
`krea2/krea2-harness/target/release/krea2`).

NOT URL-runnable: this is a compiled Rust binary, not a `uv run` script.
