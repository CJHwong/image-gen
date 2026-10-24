# Models

Normal startup offers one model per workspace. `--all-backends` exposes optional models; it does not install their weights.
[Set up models](../how-to/set-up-models.md) before using optional engines or checkpoints.

| Workspace | Model | API backend ID | Modes | Precision |
|---|---|---|---|---|
| Image | **Qwen-Image-2.1-Turbo (default)** | `qwen21_turbo` | Generate, starting image, instruction Edit with up to 10 references | Full precision by default; eight-step checkpoint schedule |
| Image | Qwen-Image-2.1 | `qwen21` | Generate, starting image, instruction Edit with up to 10 references | Full precision by default |
| Image | Viggle Turbo | `viggle_turbo` | Generate and Edit | Qwen base plus six-step adapter |
| Image | FLUX.2 klein-base-9B, uncensored | `flux2` | Generate and Edit with up to four references | Full precision by default |
| Video | **LTX-2.5 (default)** | `ltx25_mlx` | Generate and model-specific Edit effects | Eight-bit MLX pack |
| Video | LTX-2.3 | `ltx23_mlx` | Generate and supported Edit effects | Optional eight-bit MLX pack |
| Voice | **Drama-3 (default)** | `drama3` | Generate and Clone | Eight-bit MLX checkpoint |
| Voice | AuK | `auk_base` | Design, Clone, Edit | Eight-bit base; 32 steps, guidance 2 |
| Voice | AuK Flash | `auk` | Design, Clone, Edit | Eight-bit Flash; four steps |

Capabilities from `GET /api/v1/studio` are the runtime source of truth for supported modes, controls, sizes, templates, and limits.
Image quantization is controlled by each backend’s `quantize` setting; `-q 8` overrides the opening Image model.
Image Rewrite quantizes its rewriter as it loads when the backend sets `rewrite_quantize`. The shipped `studio.toml` sets 8, which halves a rewrite; 0, the default, keeps full precision.

## Video

LTX Generate accepts a prompt, optional image keyframes, and one audio track. A source clip in the timeline is not automatically a Generate conditioning input.
Dimensions lie on the engine’s 64-pixel grid. The current catalog supports 9–361 frames in steps of eight at 24 fps.
The 720 class is 1280×704; the 1080 class is 1920×1088.
An audio track selects the guided audio-to-video pipeline and is padded when shorter than the requested clip.
The input track is returned with the video; this route does not promise lip synchronization.

LTX-2.5 Edit exposes Day to Night, Water Simulation, Clean Plate, Deblur, Decompression, Restore, Upscale 2×, and Layout to Render.
Each effect declares its own geometry, duration, and conditioning settings.
Layout to Render requires a layout/playblast clip and one art-directed image derived from its first frame.
In Edit, choose the adapter, add both inputs through Media, and describe the finished materials and lighting.
It uses eight low-resolution steps, a trained 2× latent upscale, and three full-resolution steps with both references.
The public look image uses frame 0; Studio maps it to the engine's virtual position -1.
Keep the clip's dimensions on the 64-pixel grid and length at 8k+1 frames, at 24 fps.
The official known-good size is 1920×1088. Source audio is not preserved.
See the [official workflow](https://docs.ltx.io/open-source-model/vfx-post-production/layout-to-render).

Video Rewrite and automatic Generate enhancement use native Gemma instructions.
Image-aware enhancement reads the first keyframe. Later keyframes remain generator inputs.
An unchanged enhanced prompt and first image can reuse the current session’s enhancement result.
Edit adapter prompts are not enhanced.

LTX-2.5 **Fast mode** uses float16 transformer computation with the same eight-bit weights.
Generated details can change. See the [Fast-mode API contract](../../API.md#video-fast-mode).

## Voice

| Contract | Drama-3 | AuK / AuK Flash |
|---|---|---|
| Reference | Clean recording and matching transcript for Clone | Recording for Clone or Edit |
| Reference limit | 15 seconds | 120 seconds, 32 MiB WAV |
| Duration | Automatic | Model-specific duration controls |
| Voice direction | Inline cues in the script | Separate description or Edit instruction |
| Output | One continuous clip per script | One continuous clip per script |

The browser trims Drama-3 references to the first 15 seconds and clears a copied transcript after trimming.
API callers trim explicitly with `/api/v1/audio/trim`.
Drama-3 references normalize to 44.1 kHz; outputs and selected exports preserve native output bandwidth.
Its internal text chunks are an engine detail. Token exhaustion fails the operation instead of returning incomplete speech.
AuK Design starts with an empty description or an editable Template.

All three workspaces accept ordered API batches of up to 16 items.
The engines reuse supported models and conditioning; this does not imply parallel execution or a universal speedup.
