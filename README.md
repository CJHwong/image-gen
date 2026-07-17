# image-gen

Local, native image-generation backends for Apple Silicon. Each backend is a
self-contained directory: a thin wrapper script plus a `*-harness/` build
project. There's no shared runtime, so pick a backend and run its wrapper.

## Backends

- **flux2/**: Swift/MLX. Uncensored FLUX.2 klein-base-9B (text-to-image and
  image edit). Wrapper: `flux2/flux2`. Engine: the `flux-2-swift-mlx` submodule.
- **krea2/**: Rust/MLX. Krea 2 (txt2img, img2img, edit, pose-control).
  Wrapper: `krea2/krea2`.

Run `<backend>/<wrapper> help` for build, weights, and usage.

## Clone

    git clone --recurse-submodules git@github.com:CJHwong/image-gen.git
