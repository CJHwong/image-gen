<h1 align="center"><img src="docs/images/logo.svg" width="120" alt=""><br>image-gen</h1>

A local multimedia studio for Apple Silicon image generation and video pipelines. Write a prompt, share still references, and move frames between the two workspaces. The server saves no prompt or image. Your browser keeps results until you clear them.

![The page after an edit: the elevator's beach door turned into a snowstorm, with the before and after slider on the print](docs/images/hero.jpg)

## Get started

This walk-through makes the image above: first a beach outside an elevator, then the same elevator in a snowstorm. It needs a Mac with Apple Silicon and [uv](https://docs.astral.sh/uv/). It was built on a machine with 64 GB of memory.

1. Clone the repo and start the page. The server does not load model weights at startup.

       git clone git@github.com:CJHwong/image-gen.git
       cd image-gen
       uv run studio

   When the terminal says "Ready", open http://127.0.0.1:8765. The first image run downloads the official Qwen Turbo checkpoint, about 32.5 GB.

2. Paste this prompt into **Prompt**, pick **16:9** under **Size**, and press **Generate**.

       A realistic architectural photograph from inside a slightly old office elevator. Beige walls, scratched stainless-steel doors, fluorescent ceiling light. The doors are open, but instead of an office hallway there is a sunny tropical beach directly outside, with sand beginning exactly at the elevator threshold. Shot with a 24mm lens, neutral exposure, extremely realistic materials, no surreal color grading.

   The top bar counts the steps and the time left. The image took 105 s on the test machine.

   ![The beach image on the page, with its caption and facts under the print](docs/images/generate.jpg)

3. Press **Edit this** under the image. The page switches to **Edit** and takes the image as the one to change. Paste this into **What to change**, then press **Edit**.

       Keep the elevator interior exactly unchanged. Change the beach outside into a snowy mountain landscape during a mild snowstorm. Add a small amount of windblown snow accumulating just inside the elevator threshold. Match the cold outdoor light spilling into the elevator while preserving the original fluorescent indoor lighting. Photorealistic and physically plausible.

   ![The Edit form with the beach image as the image to edit and the snow prompt filled in](docs/images/edit.jpg)

4. The edit took 143 s. Drag the line across the result to compare before and after. The badge under the print reads "Edited from 01": click 01 to go back to the beach. Click the caption to read the whole prompt.

Both images stay in the strip at the bottom, also after a reload.

## How to

- **Use another port:** `uv run studio --port 9000`.
- **Use full Qwen-Image-2.1:** `uv run studio --backend qwen21`.
- **Use Viggle Turbo:** `uv run studio --backend viggle_turbo`.
- **The image weights load at full precision.** `quantize = 0` in `studio.toml` is the default for every image backend. A run on 2026-10-19 measured bf16, int8, int6 and int4 and found no level faster than another: two identical bf16 runs differ by more than any level difference. int8 costs 1.7074 of 255 mean against bf16, a 31.04 dB match, and saves memory that this machine does not need: 8.19 GB resident against 14 GB, and a 34 GB peak against 41 GB, because the load holds the dense component and its result at once. Ask for int8 with `-q 8` when memory is the constraint.
- **Use FLUX.2:** set up its weights (see [Models](#models)), then `uv run studio --backend flux2`. The title of the page becomes an image-model menu. Add `"flux2"` to `visible_backends` in [studio.toml](studio.toml) to offer it every time.
- **Choose a video model:** open the Video workspace. Its model selector uses `default_video_backend` and `visible_video_backends`, separate from image models.
- **Write a prompt the model follows:** start from the **Templates** menu, and add a style from the **Look** section. Each model offers only the Look options that passed a test on it. [PROMPTS.md](studio/l3_interface_adapters/gateways/PROMPTS.md) has the tests.
- **Finish an image:** in **Edit**, the **Look** section holds the finishing rows: exposure, white balance, grade, lens, a film finish, and retouch. A Retouch pick wants an area, so draw the mark first and the page names it in the sentence. The mark says where to look, not what may change: the change can still reach past it, which [PROMPTS.md](studio/l3_interface_adapters/gateways/PROMPTS.md) measures. The other rows are whole-frame, with or without a mark.
- **Edit several pictures at once:** put each one in **Images to edit**, and set the choice under the list to one result each. Each image is edited on its own, and every result lands beside the picture it came from, with its own before and after. Left as one picture, several images are composed into a single new image instead. The words in the prompt box lead every image, and the row beside a thumbnail adds what that one needs. A press of **Rewrite** writes a row from its own picture, and you can correct it. A batch whose every row carries words runs with the prompt box empty, the way a marked region already does.
- **Reuse a seed or a prompt:** open the **⋯** menu under the image. It also offers the image as a reference for the next run.
- **Keep an image outside the browser:** use the download button under the image.
- **Work in private:** open the theme menu (the aperture button, top right) and turn off **Keep in this browser**. This clears saved images and videos. New outputs stay in the tab until a reload.
- **Change the theme:** pick one in the theme menu. The page remembers it.

  ![The four themes: Darkroom, Leica M, Kodak Instamatic and Polaroid SX-70](docs/images/themes.jpg)

- **Work on the page without a model:** `uv run studio --stub`. Image runs return placeholder images. Video requests return metadata only, with no fake video file. The stub uses no GPU.
- **Share media between workspaces:** use image references as Video keyframes. Capture a timeline frame for Image or set it as a Video keyframe with a target frame and strength.
- **Add video sources:** use the Video controls in the right sidebar. One **Add media** door takes both kinds, and a drop or a paste goes through it too; the file's own type decides whether it becomes an image keyframe or a source clip. Image keyframes and generated clips stay in separate galleries.
- **Track and cancel a video render:** progress appears in the preview. Each tab follows and cancels only its own render. Cancel keeps the prompt and references. Each clip records its seed, settings, elapsed time, and prompt.
- **Drive the models from a script:** the page and the JSON API run the same use cases. `GET /api/v1/studio` names the models, modes, sizes, Looks and templates. Then `POST /api/v1/images/generate`, `/api/v1/images/edit`, `/api/v1/images/rewrite`, `/api/v1/videos/generate`, `/api/v1/videos/edit` and `/api/v1/videos/rewrite` take a JSON body, and `/api/v1/progress` reads the run. Images answer as base64 PNG, a clip answers as the MP4 with its seed in `X-Studio-Seed`. The OpenAPI document is at `/api/v1/openapi.json`, and the page's manual links to it. A request made while another run holds the GPU answers `409`.

  ```sh
  curl -s localhost:8765/api/v1/images/generate \
    -H 'Content-Type: application/json' \
    -d '{"prompt": "a red pear on a table", "seed": 7}' \
    | jq -r '.images[0].png_base64' | base64 -d > pear.png
  ```

## Reference

### Command line

| Flag | Default | What it does |
|---|---|---|
| `--port` | `8765` | The port of the page. |
| `--host` | `127.0.0.1` | The address the server binds. |
| `--backend` | `default_backend` | Open on this image model, and add it to the image models the page offers. |
| `-q`, `--quantize` | the `studio.toml` value | Quantize the weights of the opening model: 0 for full precision, or 3, 4, 5, 6 or 8 bits. |
| `--config` | `studio.toml` | The settings file. |
| `--stub` | off | Fake every engine: timed steps and placeholder images, no weights. |

### Settings in studio.toml

| Key | What it sets |
|---|---|
| `default_backend` | The model the page opens with. |
| `visible_backends` | The models the page offers. With more than one, the title becomes a menu. |
| `default_video_backend` | The video model selected when the page opens. |
| `visible_video_backends` | The video models the Video workspace offers. |
| `[qwen21] quantize` | 0 for bf16, or the bits for quantized weights. |
| `[flux2] quantize` | The bits for the FLUX.2 weights. |
| `[flux2] model_dir` | The folder of the FLUX.2 weights. |
| `[viggle_turbo] quantize` | 0 for bf16, or the bits for the base weights. |
| `[viggle_turbo] lora_path` | The Viggle Turbo adapter, 1.3 GB. The README has the download. |

### Keys

| Key | What it does |
|---|---|
| Cmd+Enter | Run, from anywhere on the page. |
| Left and Right arrows | Show the previous or next image in the strip. |
| F | Full screen. |
| Escape | Close a menu, or the whole prompt over the print. |

### Models

| Model | Adapter | Modes | Weights |
|---|---|---|---|
| Qwen-Image-2.1-Turbo (default) | `gateways/qwen21_turbo` | generate, img2img, and instruction edit with up to 10 images, on the checkpoint's own 8-node schedule | downloads on first image run, about 32.5 GB |
| Qwen-Image-2.1 | `gateways/qwen21` | generate, img2img, and instruction edit with up to 10 images, through mflux (MLX) | downloads on first use |
| Viggle Turbo | `gateways/viggle` | the same modes, in six steps | Qwen base weights, plus a 1.3 GB adapter |
| FLUX.2 klein-base-9B, uncensored | `gateways/flux2` | generate and img2img, edit with up to 4 images, all through mflux (MLX) | manual setup below |
| LTX-2.5 q8 (video default) | `gateways/mlx_video` | text-to-video, still-keyframe video and an audio track, through an MLX port at 8 bits | its q8 pack downloads on first run from a gated repo, about 72 GB |
| LTX-2.3 q8 | `gateways/mlx_video` | the same three jobs through the same port | its own q8 pack, about 72 GB |
| LTX-2.5 (PyTorch) | `gateways/ltx25` | the same, plus Edit with the Creative Lab effects and the pipeline's own prompt enhancer | six split files download on first video generation, about 71 GB; two more, about 51 GB, on the first run with a track |

**One model is offered, so the page draws no model picker.** `studio.toml` names the one the page opens on, and the picker appears only when there is something to pick between. Two start arguments change that: `--backend qwen21` opens on another model and adds it to the list, and `--all-backends` offers every configured model, flux2 included. The weights load at full precision by default (`quantize = 0`); `-q 8` asks for int8 instead.

**The prompt aids are per model.** A Look option or a template appears only after it passes a test on that model. The official Turbo checkpoint offers the base model's aids, because they were sampled on its own eight-node table on 2026-10-16: all 31 generate options, 15 edit options and 15 templates ran beside their own bare fixtures. Thirty of the 31 generate options landed, and only Deep focus did not, which is documented rather than cut, since this backend's catalog is the base model's by design. Its cost fits were measured on that table on an M5 Pro with BF16 weights, with and without a starting image, and its reference estimate follows mflux's remaining steps at the selected strength. The generated images still need visual review. Qwen-Image-2.1 offers 31 Look options and 15 templates, and its edit form offers 15 more options in six rows. Viggle Turbo offers only the prompt aids its six-step sample kept. FLUX.2 offers the 11 options and 8 templates it was tested with. The tests and limits are in [PROMPTS.md](studio/l3_interface_adapters/gateways/PROMPTS.md).

**Marking a region.** In edit mode, **Mark a region** turns the print into a drawing surface: a brush in three widths, four colours, a loupe that follows the brush at three times the size, undo and clear. It needs an image from the strip, because the brush draws on the print and an upload has no print. Each region travels as a last, separate image, in the palette colour that names it, on black, and the prompt names that image and each area's colour. Measured on Qwen-Image-2.1 with the mask and the sentence the page sends, one seed and 20 steps, on a drawn shape whose edge the mark matched: the change landed 15.8 times more inside the marked area than outside it, and the rest of the frame moved by 4.3 of 255. On the fixture the earlier figure came from, rebuilt from what [PROMPTS.md](studio/l3_interface_adapters/gateways/PROMPTS.md) records, the same edit scored 28.8 against 37.5 on the diffusers engine this repo has since removed, and on a mark over a patch of a uniform surface 3.1 against 2.4. The two engines are comparable and neither dominates; one seed on one fixture is not a benchmark either way. Where the mark's edge meets the object's, the mark's own colour does not appear; where a hand-drawn mark reaches past its object it can, which is the next paragraph's point. The wording is not what carries it: naming the colour scored the same as naming the image, within noise. And the figure is only ever a statement about the picture it was taken on. Measured again on 2026-10-06, in one run through one metric: a mark over a uniform surface scores 3.1x, one that matches a filled object's own edge 15.8x, and the circle fixture 28.8x, with the same recolour inside all three times and the whole difference in what changed outside. A region figure is a property of the scene as much as of the tool, and two figures from two scenes say nothing about either. Viggle Turbo offers the tool as well, on its own measurement: at six steps a mark holds where the marked area is an object's own edge, 21.0x against the base model's 28.8x on the same scene, and bounds a patch of uniform surface no better than the base does, 2.2x against 3.1x. Its page path was proven end to end as well, on three marks drawn on the print: the run whose mark followed the object's edge scored 25.8x. FLUX.2 does not offer the tool, because it has not been tested with a region. The verdicts, and what the numbers do and do not settle, are in [PROMPTS.md](studio/l3_interface_adapters/gateways/PROMPTS.md).

**The marked area is what gets repainted.** The extent of the change is the area the mark covers, not the object under it: measured at 22.0% coverage the change spilled 21.4% past the object, against 14.0% at 18.9% coverage, and neither the mask's colour nor the roughness of its edge moved that. So keep the mark close to what should change, and reach for the thin brush on anything small.

The image adapters generate through MLX, so image generation runs on Apple Silicon. A real studio refuses to start where MLX is missing. The `--stub` option still works there. Porting image generation to another vendor is not built. See [PORTABILITY.md](studio/l3_interface_adapters/gateways/qwen21/PORTABILITY.md).

**Qwen-Image-2.1-Turbo.** The default uses the official full checkpoint, not Viggle's LoRA. On the first image run, it downloads `Qwen/Qwen-Image-2.1-Turbo` into `[qwen21_turbo].model_dir`. Set that path to use another disk or a preloaded checkpoint. The server starts before it loads model weights. It samples the checkpoint's own eight-node sigma table, so eight steps is the count and no other is offered, and its time estimates were measured on that table with BF16 weights. "Why it looks like this" has the measurement and the reason.

**Qwen-Image-2.1.** The weights are `Qwen/Qwen-Image-2.1` on HuggingFace. They are not gated, about 33 GB in bf16. They download into `~/.cache/huggingface` on the first run (`HF_HOME` moves the cache).

**Viggle Turbo.** The base weights are the 33 GB above, so nothing else downloads them. What has to be fetched by hand is Viggle's distilled adapter, 1.3 GB, into the folder `lora_path` in `studio.toml` names:

       D=~/Library/Caches/models/viggle-turbo
       hf download Viggle/Qwen-Image-2.1-viggle-turbo \
         Qwen-Image-2.1-viggle-turbo-v0.3-6step-lora-r256.safetensors --local-dir "$D"

Use `hf`, not `huggingface-cli`: huggingface_hub 2.x deprecated the old name, and it now exits without downloading anything.

The adapter is passed to the model unmerged, which is what its card asks for: mflux merges by default, and merging into bf16 loses about 30 percent of what the adapter changes. Six steps is the only step count it was trained for, so the page offers no other, and it runs without guidance, so there is no negative prompt to set. It offers no Looks, no templates and no region marking yet: those were tested on the 40-step base and not on this schedule.

**LTX-2.5 video.** The first video generation downloads six required files from the gated official model into `[ltx25].model_dir`. Later runs reuse them. The server reads `python_path` and `model_dir` from `studio.toml`.

**MLX q8 video, the default.** The two q8 packs run through [ltx-2-mlx](https://github.com/dgrauet/ltx-2-mlx), a third-party MIT port. Install it outside this repo:

       git clone https://github.com/dgrauet/ltx-2-mlx.git ~/ltx-experiments/ltx-2-mlx
       cd ~/ltx-experiments/ltx-2-mlx && uv sync --all-extras

`[mlx_video]` names the port's executable, `ffmpeg`, and the two pack ids. The 2.5 pack is gated: accept its terms once at https://huggingface.co/dgrauet/ltx-2.5-mlx-q8, and the port downloads the pack on its first run. Measured on the office M5 Pro at 384 x 384 and 121 frames: 40.9 s from text on 2.5 q8 against 164.7 s on the PyTorch path, and 45 to 48 s for two keyframes against 157.8 s. A track enters the port's audio-to-video task and is padded with silence to the clip's length, because the port refuses a shorter one. The q8 packs offer Generate only: the port has no 2.5 task LoRAs, and its 2.3 LoRAs are control models that need a control video. Edit and the enhancer stay on the PyTorch model.

**A track for Generate.** Generate takes one audio track. A run that carries one enters the audio-to-video pipeline instead of the distilled one: it runs the full model in its first stage, refines with a distilled LoRA, and takes the same image keyframes as a plain run. Those two files are not among the six, so the first run with a track downloads them into `model_dir` too, 50.9 GB. The clip keeps the duration the form names and the track is trimmed to it, at 24 fps. The pipeline freezes the track in both stages and returns the original waveform, so the audio you give it is the audio you get back. That is the sound, not the mouth: a face in the frame moves as a speaker does, and its mouth motion follows the track at r 0.44 at best, so the form does not promise lip sync. The guide's own lip-sync route is the Dub-It in-context LoRA, which is a different pipeline and whose weights are gated on Hugging Face.

The video form's rewrite switch, which starts on, lengthens the prompt twice: once with the studio's own rewriter, where the longer text can be read and edited, and once inside the pipeline with the video model's own enhancer. That second pass needs a checkpoint the weight download above does not know, so fetch it once and point `[ltx25].prompt_enhancer_gemma_root` at it:

       hf download google/gemma-4-E2B-it --local-dir ~/Library/Caches/models/gemma-4-E2B-it

The q8 2.5 pack has no enhancer, so that second pass runs only on the PyTorch model.

About 10 GB. Without it a run whose switch is on refuses with that line rather than failing inside the pipeline over a path. The pipeline replaces the prompt with what that pass writes and logs it as "Enhanced prompt: ...". The runner reads the child's output for its step markers and drops the rest, so a clip's record names the text the studio sent rather than the text the transformer read.

Accept the model terms and run `uv run hf auth login` once before the first video generation. The required weights total about 71 GB. The official LTX-2 source supports Apple MPS and CUDA. Install its Python runtime once:

       git clone https://github.com/Lightricks/LTX-2.git ~/Workspace/LTX-2
       cd ~/Workspace/LTX-2
       uv sync

The Video source panel sits beside its prompt in the right sidebar. Image references become keyframes. Source clips stay separate from generated video results. The timeline can capture a clip frame as an image keyframe or send it to the Image workspace. The imported clip itself is not a video-conditioning input.

**Video has two modes, the way Image does.** **Generate** draws a clip from the prompt, with optional image keyframes and one audio track. **Edit** changes a clip the strip is holding, with an effect from the [LTX-2.5 Creative Lab](https://huggingface.co/collections/Lightricks/ltx-25-creative-lab): pick the clip in the video gallery, pick the effect, and the run posts the clip's own bytes. The effects are LoRAs on the same base the studio already runs, one file each, so an effect costs the download and nothing else. Each one carries the prompt it answers to, because they are triggered: three answer to a literal word (`ADD WATER`, `DEBLUR`, `ENHANCE QUALITY`), one wants the empty scene described rather than the thing to remove named, one asks for a clean capture back from damaged footage, and Day to night is the sixth that the box would never guess. Picking an effect seeds that text into the prompt box, and only into an empty box or over another effect's own words. Templates are a Generate aid and are hidden in Edit: one camera move, a held first or last frame, a product turn, two to four shots with each cut named, a two-person exchange with quoted lines, and a specific soundscape with no music. Generate also carries the sampled Look rows: light, atmosphere, grade, and the mix. A Look pick appends one sentence after the prompt, the way the image form's Look does, and the clip's record names the picks. They come under the LTX-2.x Community License, which allows commercial use below 10 million USD of entity-wide annual revenue. On the q8 packs the form offers Generate only; the PyTorch model carries Edit.

**Five effects ship and two do not**, on 2026-10-19 evidence rather than on the collection's size. Each of the six ran one clip at 768 × 448 and 97 frames, seed 7, with its card's own prompt at the strength the card names, and each was judged at frame 40 against its own input. Water simulation wets the road under the crossing and Clean plate empties it of people and vehicles. Colorize, Deblur and Decompression cannot be judged on the clip the others ran, because it is already in colour, already sharp and already clean, so each was re-run against a clip that carries its defect: Deblur restores focus, edge energy 1.488 to 4.374 against 9.080 for the same scene shot clean, and Decompression removes the blocking, 1.1762 to 1.0548 against a clean 1.0306. Both leave a clean clip alone, which is what a restoration effect should do, and the hint on each one names the input it wants. Colorize added no colour to a desaturated clip, 0.49 mean chroma against 0.00 in and 11.5 for a colour clip of the same scene, and a second run with its card's stage-1-only recipe reached 2.96, still grey to the eye, so it is not offered. The pixel spatial upscaler is out on mechanism: its card wants a reference at half the target's linear resolution, its own run died inside the video VAE encoder on a clip 224 pixels tall because the down block splits a latent height of 7 by 2, and the form picks the output shape from the clip's ratio rather than at twice its size. That pair needs the reference on the 64 pixel grid and the target on the 128 pixel grid, which 7 of the 16 rungs break.

**An effect is fetched by hand**, the way the enhancer's Gemma is: the weight download above knows the one base model. The file lands flat in `[ltx25].lora_dir`, and a run that asks for an effect whose weights are missing says where they go.

       uv run hf download Lightricks/LTX-2.5-22b-IC-LoRA-Day-To-Night --local-dir ~/Library/Caches/models/ltx-2.5-loras
       uv run hf download Lightricks/LTX-2.5-22b-IC-LoRA-Water-Simulation --local-dir ~/Library/Caches/models/ltx-2.5-loras
       uv run hf download Lightricks/LTX-2.5-22b-IC-LoRA-Clean-Plate --local-dir ~/Library/Caches/models/ltx-2.5-loras
       uv run hf download Lightricks/LTX-2.5-22b-IC-LoRA-Deblur --local-dir ~/Library/Caches/models/ltx-2.5-loras
       uv run hf download Lightricks/LTX-2.5-22b-IC-LoRA-Decompression --local-dir ~/Library/Caches/models/ltx-2.5-loras
       uv run hf download Lightricks/LTX-2.5-22b-IC-LoRA-Restore --local-dir ~/Library/Caches/models/ltx-2.5-loras

The selected video model supplies its frame shapes and default, duration limits and step, duration presets and default, frame rate, seed range, reference limit, and reference strength controls through `VideoCapabilities`. LTX opens on the square, as the image form does, and its lowest rung is a 384 × 384 frame. It supports 9 to 361 frames in steps of 8 at 24 fps, and its duration presets use 121, 241, and 361 frames. The UI sends an explicit frame count so the timeline and keyframes have a fixed target. The pipeline runs in a child process, which releases its model weights when generation ends. The two-stage LTX pipeline requires both dimensions to be multiples of 64, so every frame size it offers sits on that grid.

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
- **One engine for qwen21.** Generate and instruction edit both run through mflux on MLX. Editing needs the Qwen3-VL vision tower, which mflux ported in 0.21.0; before that it ran on a diffusers pipeline in a child process, which held 38.7 GiB on MPS and had to free the mflux model before every edit.
- **Viggle Turbo runs six steps and no more, after spiking its nine-step mode.** Its card offers a second mode: seven steps on the adapter, then the adapter off and two steps on the base model, on a wider sigma table. Both halves are reachable from here, mflux's scheduler registry takes a nine-node table by name and a runtime adapter switches off when each layer's scale is set to zero, and both were proved working on real weights. It still does not win. On one scene and one seed, nine steps scored 21.1x containment against six's 21.2x, so it buys nothing where six steps is weak, and it took 38.2s against 27.3s. The only visible change was on a plain generate, where nine steps kept more glaze detail and added background grain. A spike that does not win is still worth the run: it is the difference between a mode that was measured and one that was assumed.
- **A batch is images in a row, not a real batch.** On this machine a batched flux2 run was 2 to 8% slower per image than one at a time, and it used more memory. One at a time also shows each image as soon as it is done.
- **A video render shows one percentage for both of its stages.** This is the PyTorch path; the MLX port prints its own bar for each stage, so a q8 run's count starts again when stage 2 begins. The LTX-2.5 distilled pipeline denoises a clip twice: once at its own resolution, then again after the spatial upsampler. The runner asks for one window and passes no chunk flags, so each stage samples once, and both stages arrive as one count of steps so the number cannot reset halfway through. Measured on the office machine, one 5 second 1024x576 clip: the pipeline logged 8 steps then 3, and the page read step 1 of 11 at 72s and step 9 of 11 at 150s. The sampler also breaks out of its loop on the terminal sigma instead of running its iterator dry, so a step is reported as it starts. A report written after the iterator's yield never fired for a stage's last step, and the bar parked at 10 of 11 for the rest of the run.
- **An audio track takes the guided pipeline, and it costs about 2.5 times a plain clip.** Generate enters `a2vid_two_stage` when a track is attached: the full model at half resolution for 30 guided steps, then the distilled refinement. Measured on the office M5 Pro on 2026-10-19, one 384 x 384 clip of 25 frames at seed 7, with the same prompt and reference: 243.4 s with a track against 91.4 s on the distilled path. The reference survives the switch. A frame-0 keyframe of a red disc on green came back at 19.7% red against the reference's 19.8%, in a box within one pixel of it, 96..287 against 96..288. Without the reference the same run made a different scene, 13.9% red in an off-centre blob and almost no green, so the frame is the reference and not the prompt. The track returns unchanged: 440 Hz in, 439.7 Hz out over the clip's 1.042 s. Every track is decoded to stereo PCM before the render, because the audio VAE's first convolution takes two channels and a mono WAV died there with `expected input[1, 1, 107, 66] to have 2 channels`. Only the clip's own seconds are decoded.
- **An edit keeps the scene and changes its light, and the people move differently.** Measured on the office M5 Pro, one daylight clip of 97 frames at 768 x 448, seed 7, through `ltx_pipelines.ic_lora`: the frame darkens from 107.2 to 39.2 mean luminance, the buildings, the street and the crosswalk hold, and the crowd is re-synthesised rather than preserved, so a figure crossing left in the input may cross right in the output. The card says the same thing in its own words, that the reference drives structure and the prompt drives the lighting. Two stages with stage 2 bare is worse than that: the market stall in the input comes back as a parked car, which is what `--stage-2-ic-lora` is for, and every effect's own declaration carries whether it wants it. The single-stage recipe several cards name was measured too, at 1536 x 896 so its half-resolution output lands on 768 x 448, and it did not keep the stall either, so the two-stage path with the conditioning kept is what the form drives.
- **The transformer is built once per clip, not once per stage.** A stage builds its transformer for each denoise pass and frees it when the pass returns, so one clip read the 39.1 GB file twice, 78 GB of the 115 GB a clip loads. The runner's wrapper keeps the first build and hands the same model to the second pass, then frees it when that pass ends, which is the last one: the pipeline runs one denoise pass per stage, its two stages are the two calls in `stream_chunks`, and the decode that wants the room comes after them. The build does not depend on the shape of the latents, because the single GPU builder ignores the video tools the stage hands it, so no shape enters the build; that was checked at the one shape measured here. Measured on the office M5 Pro, one 384 x 384 clip of 73 frames: the second build cost 32.4 s and 36.2 s in two runs, and with the hold the second pass entered its denoising loop in the same millisecond as its build line, against a 32.4 s gap without. Both runs made the same clip: 73 of 73 frames identical and no audio difference. The block streaming path is left alone, because it frees its blocks between passes by design. At the largest shape the form offers, 1280 x 704 at 73 frames, the second build cost 40.0 s without the hold and 0.003 s with it, and the hold's own window, which covers the upsampler, cost 1.3 s there, 1.9 s against 3.2 s. The two runs' totals are not comparable and I do not quote them as a gain: the run with the hold took 499.8 s against 393.2 s, and all of that difference sits in the first stage, whose first step took 131.7 s against 26.7 s. That step swings with the machine rather than with this change, because the plain wrapper measured 20.1 s and 110.3 s at 384 x 384 in the same evening. The release lands before the decode builds its VAE, so the decode cannot see the hold at all.
- **A clip's first denoise step cost 20 s to 110 s in the runs measured, and the machine's memory moved with it.** On the office M5 Pro, one 384 x 384 clip of 73 frames: the first step of the first stage took 20.1 s and 30.5 s in two runs with the machine to itself, and 110.3 s in a run while the studio's own server was up, RAM held 63 GB of page cache, and swap held 7.7 GB of 9 GB. Those runs differ in more than one thing, so this points at the memory without proving it. The steps after the first cost 0.8 s to 4 s. A clip is 11 steps whatever its length, because the distilled schedule is a table: 3 seconds of video and 15 seconds of video run the same steps, and length changes the tokens in each step and not the count. So a 15 second clip costs about twice a 3 second one and not five times, and the wait is the load and the first use rather than the frames.
- **The Turbo checkpoint is sampled on the table it ships.** mflux builds `linspace(1, 1/steps, steps)` plus a zero for this checkpoint and never reads the `sample_sigmas` it carries: the grep for that name over the mflux package finds nothing, and the model card says the opposite, that the table "is loaded automatically" and that `num_inference_steps` alone does not override it. So `gateways/qwen21_turbo_schedule.py` registers the checkpoint's own eight nodes as a scheduler, the way mflux registers Viggle's six, and eight nodes means eight steps. Measured 2026-10-16 on the office machine, one prompt and two seeds at 768 x 768: the two tables differ by RMS 26.3 and 35.3, as much as 8 steps differ from 40, and the linear table carries 2.5 to 3.1 more edge energy. Two seeds and one prompt say which way a schedule moves a picture, not which is better; the shipped one is the publisher's own and the one they evaluated. Both were also timed at 8, 20 and 40 steps, which is a flat 1.41 s/step with about 0.6s of fixed cost at 768 x 768, and detail stops improving past 20: edge energy reads 18.28, 19.11 and 19.36 at 8, 20 and 40 steps.
- **One run at a time.** The GPU is full with one run, and two only slow each other. A run from a second tab gets a message to wait, not a place in a queue.
- **One model family in memory.** Image and video workspaces keep separate model choices, but they share one memory slot. The server loads weights only when a run needs them. A workspace switch releases the inactive model. Prompt rewriting uses the same lock and releases its weights when the rewrite ends. Within a run, a model the run uses more than once is held until its last use, and a model it uses once is freed when that use ends. The video transformer is the one held today, and a batch of images holds its engine for the whole batch. A clip builds its video encoder twice as well, 0.59 GB and about a second of the upsampler's 2.4 s, and that one is left alone: sharing it means either copying two blocks' own call bodies, which would drift from the pipeline and could skip the upsample step itself, or caching inside the loader that builds it, which risks handing back the wrong model. Neither is worth 0.7 percent of a clip. The sizes decide what can be held together: on a 64 GB machine the LTX transformer is 39.1 GB and the text encoder it needs beside it is 24.5 GB, which is 63.6 GB of the machine and leaves nothing for macOS and the server, so those two are never resident together and a clip loads them in turn. A workspace switch is what gives the slot back.
- **The server keeps nothing, and it binds 127.0.0.1.** It holds neither the prompt nor the image. An edit does write its reference images into a temporary directory for the length of that one run and removes it afterward, because mflux's edit call takes paths rather than images. That is the only thing this server puts on disk. The browser keeps the images in its own storage, which belongs to the address and port, so a server on another port shows an empty strip.

## Licenses

The weights keep their own licenses. Qwen-Image-2.1 is under the Qwen Research License, which allows research use only, and Viggle's adapter for it is under the same license. FLUX.2 klein-base-9B is under the FLUX Non-Commercial License. Check them before you use any output commercially.
