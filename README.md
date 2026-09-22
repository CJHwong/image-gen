# image-gen

Local, native image-generation backends for Apple Silicon. Each backend is a
self-contained directory: a thin wrapper script plus a `*-harness/` build
project. There's no shared runtime, so pick a backend and run its wrapper.

## Backends

- **flux2/**: Swift/MLX. Uncensored FLUX.2 klein-base-9B (text-to-image and
  image edit). Wrapper: `flux2/flux2`. Engine: the `flux-2-swift-mlx` submodule.
- **krea2/**: Rust/MLX. Krea 2 (txt2img, img2img, edit, pose-control).
  Wrapper: `krea2/krea2`.
- **qwen21/**: Qwen-Image-2.1, two engines behind one wrapper. `qwen21` runs
  txt2img and img2img through mflux (Python/MLX); `qwen21 edit` runs instruction
  editing through diffusers (PyTorch/MPS), because mflux has not ported the
  Qwen3-VL vision tower that editing needs. `qwen21 server` puts all three on a
  local web page, running the edit engine as a child process, and writes nothing
  to disk, neither the prompt nor the image. Nothing to build. Weights are under
  the Qwen Research License, so research use only. Wrapper: `qwen21/qwen21`.

Run `<backend>/<wrapper> help` for build, weights, and usage.

## Clone

    git clone --recurse-submodules git@github.com:CJHwong/image-gen.git
