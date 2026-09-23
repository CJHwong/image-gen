# image-gen

Local image generation on Apple Silicon. Each backend is one directory with one wrapper script.

## Quick start

1. Clone the repo.

       git clone git@github.com:CJHwong/image-gen.git

2. Pick a backend and read its setup. Each `help` lists the weights to download and, for krea2, the build step.

       qwen21/qwen21 help

3. Generate an image.

       qwen21/qwen21 --prompt "a red apple" --output apple.png

## How to

- **Make an image from text:** `flux2/flux2 --prompt "..." --output out.png`, or the same flags on `qwen21/qwen21`.
- **Change an existing image:** add `--input ref.png` to `flux2`, or `--image ref.png 0.6` to `qwen21`.
- **Edit an image by instruction:** `qwen21/qwen21 edit --prompt "make it night" --image room.png`, or `krea2/krea2 edit --prompt "..." --source src.png -o out.png`.
- **Control the pose:** `krea2/krea2 control --prompt "..." --pose pose.png -o out.png`.
- **Use a web page instead of the command line:** `qwen21/qwen21 server`, then open http://127.0.0.1:8765.
- **Write a prompt that qwen21 follows:** start from a template in [qwen21/PROMPTS.md](qwen21/PROMPTS.md), or from the Templates menu in the page.
- **Run a wrapper from anywhere:** symlink the wrapper into your `PATH`, for example `ln -s "$PWD/qwen21/qwen21" ~/.local/bin/qwen21`. `qwen21`, `flux2` and `flux2-gen` follow the symlink back to the repo. `krea2` does not, so call it by its path.

## Backends

| Backend | Model | Engine | Modes | Build |
|---|---|---|---|---|
| `flux2/flux2` | FLUX.2 klein-base-9B, uncensored | mflux (Python/MLX) | txt2img, img2img | none |
| `flux2/flux2-gen` | same as `flux2` | same as `flux2` | reads a multi-line prompt, then calls `flux2` | none |
| `krea2/krea2` | Krea 2 | mlx-gen (Rust/MLX) | txt2img, img2img, edit, control | `cargo build --release` |
| `qwen21/qwen21` | Qwen-Image-2.1 | mflux (MLX) | txt2img, img2img | none |
| `qwen21/qwen21 edit` | Qwen-Image-2.1 | diffusers (PyTorch/MPS) | instruction edit | none |
| `qwen21/qwen21 server` | Qwen-Image-2.1 | both of the above | a local web page for all modes | none |

Every wrapper prints its flags, defaults and environment variables with `help`.

## Why it looks like this

- **No shared runtime.** The engines come from unrelated projects in Python, Rust and PyTorch. A shared layer would couple their upgrades, so every backend stands alone.
- **Two engines for qwen21.** mflux is faster and quantizes, but it has no port of the Qwen3-VL vision tower that instruction editing needs. So editing runs on diffusers.
- **The edit VAE encoder runs on the CPU.** MPS computes it wrong, and every reference image comes out washed out. [qwen21/MPS-VAE-ENCODE.md](qwen21/MPS-VAE-ENCODE.md) holds the measurements.
- **The qwen21 server writes nothing to disk.** It keeps neither the prompt nor the image.

## Licenses

The weights keep their own licenses. Qwen-Image-2.1 is under the Qwen Research License, which allows research use only. Krea 2 is under the Krea 2 Community License.
