# Model setup

Open Imagine runs on Apple Silicon. Image models use the main MLX environment.
Video uses a separate pinned LTX environment; Voice children declare their own pinned environments.
Start from the repository root, and keep `uv` on the server and child processes’ `PATH`.
See [studio.toml](../studio.toml) for paths and model visibility.

**Qwen-Image-2.1-Turbo.** The default uses the official full checkpoint, not Viggle's LoRA. On the first image run, it downloads `Qwen/Qwen-Image-2.1-Turbo` into `[qwen21_turbo].model_dir`. Set that path to use another disk or a preloaded checkpoint. The server starts before it loads model weights. It samples the checkpoint's own eight-node sigma table, so eight steps is the count and no other is offered, and its time estimates were measured on that table with BF16 weights. [Design decisions](DESIGN_DECISIONS.md) records the measurements and rationale.

**Qwen-Image-2.1.** The weights are `Qwen/Qwen-Image-2.1` on HuggingFace. They are not gated, about 33 GB in bf16. They download into `~/.cache/huggingface` on the first run (`HF_HOME` moves the cache).

**Viggle Turbo.** The base weights are the 33 GB above, so nothing else downloads them. What has to be fetched by hand is Viggle's distilled adapter, 1.3 GB, into the folder `lora_path` in [`studio.toml`](../studio.toml) names:

       D=~/Library/Caches/models/viggle-turbo
       hf download Viggle/Qwen-Image-2.1-viggle-turbo \
         Qwen-Image-2.1-viggle-turbo-v0.3-6step-lora-r256.safetensors --local-dir "$D"

Use `hf`, not `huggingface-cli`: huggingface_hub 2.x deprecated the old name, and it now exits without downloading anything.

The adapter is passed to the model unmerged, which is what its card asks for: mflux merges by default, and merging into bf16 loses about 30 percent of what the adapter changes. Six steps is the only step count it was trained for, so the page offers no other, and it runs without guidance, so there is no negative prompt to set. Its available Looks, templates and region controls are declared by its capabilities; see the model-specific verdicts in [PROMPTS.md](../studio/l3_interface_adapters/gateways/PROMPTS.md).


**MLX q8 video, the default.** The two q8 packs run through [ltx-2-mlx](https://github.com/dgrauet/ltx-2-mlx), a third-party MIT port. Install it outside this repo:

       git clone https://github.com/dgrauet/ltx-2-mlx.git ~/ltx-experiments/ltx-2-mlx
       cd ~/ltx-experiments/ltx-2-mlx
       git checkout 5fed9e2a588102c231658d2a2b7be1ef7bf350b4
       uv sync --all-extras
       uv pip install --python .venv/bin/python "mlx-vlm==0.4.3" "mlx==0.32.2" "mlx-lm==0.31.1" "transformers==5.3.0"

Image-aware enhancement uses [MLX-VLM](https://github.com/Blaizzy/mlx-vlm) (MIT), the existing `mlx-community/gemma-3-12b-it-4bit` checkpoint and LTX’s native I2V instructions. Its vision weights are included in that checkpoint; the video packs and text encoder are unchanged. Studio loads the vision model only during enhancement and releases it before rendering.

`[mlx_video]` names the port's executable, `ffmpeg`, and the two pack ids. The 2.5 pack is gated: accept its terms once at https://huggingface.co/dgrauet/ltx-2.5-mlx-q8, and the port downloads the pack on its first run. Measured on the office M5 Pro at 384 x 384 and 121 frames: 40.9 s from text on 2.5 q8 against 164.7 s on the engine it replaced, and 45 to 48 s for two keyframes against 157.8 s on the engine it replaced. The form's largest rung is the 1080 class, 1920 x 1088: a generate of 97 frames took 790 s on 2.5 q8 and stayed inside 64 GB. The model's grid sets the sizes, so the 720 class is 1280 x 704. An exact 720 or 1080 side is off the 32 pixel blocks the VAE uses. A track enters the port's audio-to-video task and is padded with silence to the clip's length, because the port refuses a shorter one. On 2.3 a keyframe job takes the two-stage path, 299.5 s at 384 x 384, because the distilled path held the room until the last frame and landed the change in one step; 2.5 builds it on the distilled path already. Edit renders the seven LTX-2.5 effects on the port's single-stage path with the distilled transformer, which is the topology their cards name. Each effect runs at its measured size and length, read from the adapter rather than from the shape control. The default two-stage path applies the reference at half resolution and drops it in stage 2, so it erases the change. The effect weights are seven small gated repos on Hugging Face, about 5.9 GB for all of them. Set `[mlx_video] fetch_loras = true` and the studio fetches the one file a run needs the first time that effect runs; leave it off and the studio names the path to place the file at. Cancel stops an adapter download as well as a render. Water stays at 1280 x 704: its 1920 x 1088 single-stage edit exceeds the tested machine's memory, and the upsample-only alternative produces corrupt frames. Generate now runs the port’s separate Gemma-3 prompt enhancer before either pack; LTX-2.5 then encodes that text with its Gemma-4 tower. Edit adapter prompts are not enhanced. The older timings above predate automatic enhancement. The verdicts, sizes and timings are in [PROMPTS.md](../studio/l3_interface_adapters/gateways/PROMPTS.md).

**A track for Generate.** Generate takes one audio track. The runner pads it with silence to the clip's length, because the MLX port refuses a shorter one, then enters the port's audio-to-video task with the same keyframes. The clip keeps the duration the form names at 24 fps, and the port returns the original waveform with the clip, so the audio you give it is the audio you get back. That is the sound, not the mouth: a face moves as a speaker does, and the form does not promise lip sync. The guide's lip-sync route is the Dub-It LoRA; its 2.3 engine was removed with PyTorch on 2026-10-20, so Dub is deferred.

The Video Rewrite button is optional: it writes expanded text into the editable prompt box. Separately, every Generate call runs the pipeline’s Gemma-3 enhancer automatically, including API calls and audio-conditioned generation. This native pass does not call the Rewrite API.



Accept the model terms and run `uv run hf auth login` once before the first video generation. The required weights total about 71 GB.

The Video source panel sits beside its prompt in the right sidebar. Image references become keyframes. Source clips stay separate from generated video results. The timeline can capture a clip frame as an image keyframe or send it to the Image workspace. The imported clip itself is not a video-conditioning input.

**Video has two modes.** Generate draws a clip from the prompt, with optional image keyframes and one audio track. Templates are one camera move, a held first or last frame, a product turn, two to four shots with each cut named, a two-person exchange with quoted lines, and a specific soundscape with no music. LTX-2.5 also offers Speak to camera, Fixed composition, and Slow push-in. Six API probes established the limits of sideways and orbit prompts. Generate also carries the sampled Look rows: light, atmosphere, grade, and the mix. A Look pick appends one sentence after the prompt, the way the image form's Look does, and the clip's record names the picks. Edit changes a clip with one of seven LTX-2.5 effects: day to night, water simulation, clean plate, deblur, decompression, restore, and upscale 2x. Each effect carries its trigger prompt and strength, and picking one seeds the prompt box. An effect renders at the geometry its card trained at, so the run shape comes from the adapter, not from the clip: day to night at 768 x 448 for 97 frames, water at 1280 x 704 for 97, clean plate at 1024 x 576 for 49, deblur and decompression at 960 x 544 for 121, restore at 960 x 544 for 97, and upscale 2x at twice the clip's width and height.




The selected video model supplies its frame shapes and default, duration limits and step, duration presets and default, frame rate, seed range, reference limit, and reference strength controls through `VideoCapabilities`. LTX opens on the square, as the image form does, and its lowest rung is a 384 × 384 frame. It supports 9 to 361 frames in steps of 8 at 24 fps, and its duration presets use 121, 241, and 361 frames. The UI sends an explicit frame count so the timeline and keyframes have a fixed target. The port runs in a child process, which releases its model weights when generation ends. The port requires both dimensions to be multiples of 64, so every frame size it offers sits on that grid.

**AuK Flash and AuK (Voice).** The studio starts its resident Voice child on the first Voice job.
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
An AuK reference must contain WAV audio within 120 seconds and 32 MiB. Drama-3 permits 15 seconds.
The selected model publishes its reference duration and sample rate in capabilities.
The browser converts an uploaded or recorded reference to mono WAV before submission.
Generate creates one continuous clip for the whole script by default.
Each UI generation creates one continuous clip. The API supports explicit batches of up to 16 clips.
The action menu offers Reuse script and voice, Send to Video, and Send to Clone.
These actions prepare inputs without starting generation.
Preview metadata shows at most two lines per description. Click it to read the full text.
The player supports preview speeds from 0.5x to 2x without changing downloads.
Generate and Edit switch the preview to an animated waveform with server progress.
The finished clip replaces the animation. Select an older gallery clip to preview it during a run.
Image, Video, and Voice use the same gallery selection circle.
Voice design starts with an empty custom description or one of six editable Templates.
The templates separate speaker, texture, pace, context, and emotion from the spoken script.
They adapt the [official AuK cookbook](https://github.com/Tencent-Hunyuan/AuK/blob/9481474f107ee4d8dec959b3aed05b0627cebbf8/docs/COOKBOOK.md#12-instruct-tts)
and [demo descriptions](https://github.com/Tencent-Hunyuan/AuK/blob/9481474f107ee4d8dec959b3aed05b0627cebbf8/src/auk/infer/infer_gradio.py#L25).
Reference cloning reads new words with the supplied voice.
An edit changes the reference recording according to the offered instruction.

**FLUX.2 klein-base-9B.** mflux reads one diffusers-layout folder, and its name must contain `klein-base-9b`. The default is `~/Library/Caches/models/mflux-klein-base-9b-uncensored`; `model_dir` in [`studio.toml`](../studio.toml) moves it. It takes about 33 GB.

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

**Drama-3 (Voice).** Voice opens on Drama-3 by default. Generate accepts spoken text with optional inline directions, such as `[whispers]`. Its Whisper and Excited templates fill the script. Clone needs a clean recording and its exact reference transcript. The browser and engine normalize references to 44.1 kHz; selected and joined exports preserve native output bandwidth.

Drama-3 uses automatic duration. The selected MLX engine exposes no AuK-style Design or Edit mode, so those controls disappear. Playback speed remains a player control. One script produces one continuous gallery clip; internal text and codec chunks stay inside the engine. A token limit or a missing internal chunk fails the operation instead of publishing partial speech. Unconditioned Traditional Chinese failed an initial check; reference-conditioned Chinese passed. The engine uses 180-byte internal text chunks after larger chunks caused long-script token-cap failures; 573-character Generate and 376-character Clone scripts passed complete transcription checks with the smaller chunks.

The child pins MLX Audio commit `2209e6d76c18d0a24f7ff64d35b4176258acd909` and checkpoint revision `fedc7cc92bab5a180709cbaae6208d10b390bb97`. Its separate environment is declared in the script. To download the weights into the default Hugging Face cache before a run:

```sh
uv run --with huggingface-hub==2.2.0 hf download mlx-community/fish-audio-drama-3-8bit \
  --revision fedc7cc92bab5a180709cbaae6208d10b390bb97
```

`[drama3].python_path` can select an environment with the script's exact dependencies; otherwise `uv` builds its pinned script environment. `[drama3].child_script` selects the child script. Ordered API batches retain one engine and the reference cache. The engine does not expose parallel generation: four warm single requests took 8.62 seconds versus 8.49 seconds for the same four-item batch, with identical PCM. A later four-item Clone batch was 9% slower than warm singles, so ordered reuse does not promise a throughput gain. Sixteen short Clone items completed in 49.83 seconds for 55.40 seconds of audio, with all scripts confirmed and peak Metal allocation about 41.05 GiB. A new-process cold run took 21.79 seconds; the first API launch in a fresh script environment took 191.27 seconds including setup, loading, and first inference. Keep these separate from warm throughput.
