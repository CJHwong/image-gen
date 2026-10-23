# Set up model weights and engines

Use this guide to prepare a model before running it. Start from the repository root with `uv` on the server and child processes’ `PATH`.
Edit [studio.toml](../../studio.toml) to change engine paths or model directories.
For model capabilities and reference requirements, see [Models](../reference/models.md).

## Default Image: Qwen Image Turbo

Run an Image generation to download `Qwen/Qwen-Image-2.1-Turbo` into `[qwen21_turbo].model_dir` (about 32.5 GB).
Set that directory before starting if you want another disk or already have the checkpoint.

## Video: LTX-2.5

Install the separate pinned MLX engine outside the checkout. Install `ffmpeg` as well (`brew install ffmpeg` on Homebrew); its configured path is `/opt/homebrew/bin/ffmpeg`.

The two q8 packs run through [ltx-2-mlx](https://github.com/dgrauet/ltx-2-mlx), a third-party MIT port. Install it outside this repo:

       git clone https://github.com/dgrauet/ltx-2-mlx.git ~/ltx-experiments/ltx-2-mlx
       cd ~/ltx-experiments/ltx-2-mlx
       git checkout 5fed9e2a588102c231658d2a2b7be1ef7bf350b4
       uv sync --all-extras
       uv pip install --python .venv/bin/python "mlx-vlm==0.4.3" "mlx==0.32.2" "mlx-lm==0.31.1" "transformers==5.3.0"

Set `[mlx_video].cli_path` to the installed executable if you used a different directory.
The separate environment needs the pinned `mlx-vlm` package for image-aware prompt enhancement.
Accept the model terms at [dgrauet/ltx-2.5-mlx-q8](https://huggingface.co/dgrauet/ltx-2.5-mlx-q8), then authenticate:

```sh
uv run hf auth login
```

The engine downloads the video pack on first generation (about 72 GB).
To use Video Edit effects, accept each adapter’s terms and either place its file in `[mlx_video].lora_dir`
or enable `[mlx_video].fetch_loras`. The default leaves adapter downloads disabled and reports the missing path.
For **Layout to Render**, accept the [adapter terms](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Layout-To-Render), then download to the default adapter directory:

```sh
uv run --with huggingface-hub hf download Lightricks/LTX-2.5-22b-IC-LoRA-Layout-To-Render \
  ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors \
  --local-dir ~/Library/Caches/models/ltx-2.5-loras
```

The LTX-2.5 pack must include `spatial_upscaler_x2_v1_0.safetensors` and its `_config.json`.
Studio checks both before this adapter runs; the pinned engine otherwise silently leaves the upscaler untrained.
LTX-2.3 requires its own pack and is optional.

## Default Voice: Drama-3

The child pins MLX Audio commit `2209e6d76c18d0a24f7ff64d35b4176258acd909` and checkpoint revision `fedc7cc92bab5a180709cbaae6208d10b390bb97`. Its separate environment is declared in the script. To download the weights into the default Hugging Face cache before a run:

```sh
uv run --with huggingface-hub==2.2.0 hf download mlx-community/fish-audio-drama-3-8bit \
  --revision fedc7cc92bab5a180709cbaae6208d10b390bb97
```

`[drama3].python_path` can select an environment with the script's exact dependencies; otherwise `uv` builds its pinned script environment. `[drama3].child_script` selects the child script.
Start a Voice request after the download. The first launch can still prepare its separate dependency environment.
Keep cold setup and warm generation time separate when assessing performance.

## Optional Voice: AuK and AuK Flash

The studio starts its resident Voice child on the first Voice job.
The child uses the pinned AuK revision `6943a1e967409e8c73139a7a345f2a611cfb3dd6`.
Its script declares the separate environment, so the main environment does not need AuK installed.
Keep `uv` on the server's PATH, including for its child processes.
The child downloads `smcleod/AuK-MLX-8bit` at revision `abffd38adf7d9f0a94822e7c153e0c4ef70ef213`.
It uses the default Hugging Face cache. Set `HF_HOME` before starting the server to move that cache.
To fetch the required files before the first job:

```sh
uv run --with huggingface-hub==0.35.3 hf download smcleod/AuK-MLX-8bit \
  --revision abffd38adf7d9f0a94822e7c153e0c4ef70ef213 \
  --include 'dit_flash.q8.safetensors' 'fusion_flash.safetensors' \
    'config_flash.yaml' 'vae.safetensors' 'thinker/*' 'qwen/*'
```

`[auk].child_script` can select another copy of the pinned child script.
With `--all-backends`, the Voice selector offers Drama-3 (`drama3`, the default), AuK (`auk_base`), and AuK Flash (`auk`). Normal startup offers Drama-3 alone.
Flash uses 4 steps. AuK uses the upstream 32-step schedule and guidance 2.
Both offer the same clone, design, edit, and batch controls. A switch releases the previous model.
The selected model loads on the next job. Selecting a model does not download its weights.
AuK shares the Flash encoder and decoder files. Its additional download is about 1.75 GB.
To fetch its files before the first job:

```sh
uv run --with huggingface-hub==0.35.3 hf download smcleod/AuK-MLX-8bit \
  --revision abffd38adf7d9f0a94822e7c153e0c4ef70ef213 \
  --include 'dit_base.q8.safetensors' 'fusion_base.safetensors' \
    'config_base.yaml' 'vae.safetensors' 'thinker/*' 'qwen/*'
```
## Optional Image: Qwen and Viggle Turbo

Use `uv run studio --backend qwen21` to open on full Qwen-Image-2.1. Its approximately 33 GB weights download on first use into the default Hugging Face cache (`HF_HOME` changes the cache root).
Viggle Turbo shares that base and needs its separate adapter. Download the file to `[viggle_turbo].lora_path`:

```sh
uv run hf download Viggle/Qwen-Image-2.1-viggle-turbo \
  Qwen-Image-2.1-viggle-turbo-v0.3-6step-lora-r256.safetensors \
  --local-dir ~/Library/Caches/models/viggle-turbo
```

Then launch with `uv run studio --backend viggle_turbo`.

## Optional Image: FLUX.2

mflux reads one diffusers-layout folder, and its name must contain `klein-base-9b`. The default is `~/Library/Caches/models/mflux-klein-base-9b-uncensored`; `model_dir` in [`studio.toml`](../../studio.toml) moves it. It takes about 33 GB.

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

## Offer the installed models

Start with `uv run studio --all-backends` to show all model selectors, or configure a subset with
`visible_backends`, `visible_video_backends`, and `visible_voice_backends` in `studio.toml`.
Selecting a model does not load its weights. The next operation loads it.
See [model licenses](../reference/model-licenses.md) before choosing a model for your use.
