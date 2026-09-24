# image-gen

A local image generation page for Apple Silicon. One page, one adapter per model. No image or prompt is saved to disk. The page keeps only your theme, in the browser.

## Quick start

1. Clone the repo.

       git clone git@github.com:CJHwong/image-gen.git

2. Start the page.

       uv run studio

3. Open http://127.0.0.1:8765.

The first start downloads the Qwen-Image-2.1 weights, about 33 GB. See [Models](#models).

## How to

- **Use another port:** `uv run studio --port 9000`.
- **Work on the page without a model:** `uv run studio --stub`. Each backend keeps its form, but a run shows fake steps and returns a placeholder image. It uses no GPU.
- **Save memory on qwen21:** `uv run studio -q 8` loads the weights as int8.
- **Use FLUX.2:** set up its weights (see [Models](#models)), then `uv run studio --backend flux2`. The title of the page becomes a menu that switches between the models. To offer both every time, add `"flux2"` to `visible_backends` in [studio.toml](studio.toml).
- **Write a prompt the model follows:** use the Templates menu and the Look section in the page. Each model offers only the Look options that passed a test on it. [PROMPTS.md](studio/l3_interface_adapters/gateways/PROMPTS.md) has the tests.
- **Keep an image:** use the download button. The page keeps images in tab memory only, so a reload clears them.

## Models

| Model | Adapter | Modes | Weights |
|---|---|---|---|
| Qwen-Image-2.1 (default) | `gateways/qwen21` | generate and img2img through mflux (MLX); instruction edit with up to 10 images through diffusers (MPS) | downloads itself |
| FLUX.2 klein-base-9B, uncensored | `gateways/flux2` | generate and img2img, edit with up to 4 images, all through mflux (MLX) | manual setup below |

**Qwen-Image-2.1.** The weights are `Qwen/Qwen-Image-2.1` on HuggingFace. They are not gated, about 33 GB in bf16. They download into `~/.cache/huggingface` on the first run (`HF_HOME` moves the cache).

**FLUX.2 klein-base-9B.** mflux reads one diffusers-layout folder, and its name must contain `klein-base-9b`. The default is `~/Library/Caches/models/mflux-klein-base-9b-uncensored`; `model_dir` in `studio.toml` moves it. It takes about 33 GB.

1. Everything except the encoder weights comes from the uncensored transformer repo. It is not gated.

       M=~/Library/Caches/models/mflux-klein-base-9b-uncensored
       SRC=https://huggingface.co/darknight9121/FLUX.2-klein-base-9B-bucket-uncensored/resolve/main
       for f in model_index.json scheduler/scheduler_config.json \
                text_encoder/config.json text_encoder/generation_config.json \
                tokenizer/{added_tokens.json,chat_template.jinja,merges.txt} \
                tokenizer/{special_tokens_map.json,tokenizer.json,tokenizer_config.json,vocab.json} \
                transformer/config.json transformer/diffusion_pytorch_model.safetensors.index.json \
                transformer/diffusion_pytorch_model-0000{1,2}-of-00002.safetensors \
                vae/config.json vae/diffusion_pytorch_model.safetensors; do
         curl -L -C - --create-dirs "$SRC/$f" -o "$M/$f"
       done

2. The encoder weights come from the uncensored encoder repo. It is gated: accept its conditions on the HuggingFace page, then pass your token.

       E=~/Library/Caches/models/ponpoke-uncensored-qwen3-8b
       curl -L -C - --create-dirs -H "Authorization: Bearer $HF_TOKEN" \
         https://huggingface.co/ponpoke/flux2-klein-9b-uncensored-text-encoder/resolve/main/model.safetensors \
         -o "$E/model.safetensors"
       ln -s "$E/model.safetensors" "$M/text_encoder/model.safetensors"

   Fetch only `model.safetensors`. The `.gguf` files there are for llama.cpp.

## Why it looks like this

- **One page, one adapter per model.** The page asks the model what it supports and hides the rest. A new model is one adapter in `studio/`, and the page does not change. [studio/ARCHITECTURE.md](studio/ARCHITECTURE.md) has the layers and how to add a model.
- **Two engines for qwen21.** mflux is faster and quantizes, but it has no port of the Qwen3-VL vision tower that instruction editing needs. So editing runs on diffusers, in a child process.
- **The edit VAE encoder runs on the CPU.** MPS computes it wrong, and every reference image comes out washed out. [MPS-VAE-ENCODE.md](studio/l3_interface_adapters/gateways/qwen21/MPS-VAE-ENCODE.md) holds the measurements.
- **A batch is images in a row, not a real batch.** On this machine a batched flux2 run was 2 to 8% slower per image than one at a time, and it used more memory. One at a time also shows each image as soon as it is done.
- **Nothing is written to disk.** The server keeps neither the prompt nor the image, and it binds 127.0.0.1.

## Licenses

The weights keep their own licenses. Qwen-Image-2.1 is under the Qwen Research License, which allows research use only. FLUX.2 klein-base-9B is under the FLUX Non-Commercial License. Check them before you use any output commercially.
