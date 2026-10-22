<h1 align="center"><img src="docs/images/logo.svg" width="120" alt=""><br>Open Imagine</h1>

<p align="center">A local Image, Video, and Voice studio for Apple Silicon — with a shared UI and API.</p>

Generate and edit images, create video from text and references, and turn scripts into speech.
Use the browser or drive the same operations from an API: open tabs follow the active workspace,
progress, and results, including jobs started by scripts and agents.

![Image editing in Open Imagine, with a before-and-after comparison](docs/images/hero.jpg)

## Get started

You need a Mac with Apple Silicon and [uv](https://docs.astral.sh/uv/).
Development and real-model checks use a Mac with 64 GB of unified memory; memory and disk requirements vary by model.

```sh
git clone https://github.com/CJHwong/open-imagine.git
cd open-imagine
uv run studio
```

Open **http://127.0.0.1:8765**. Startup does not load model weights.
The first Image generation downloads Qwen Image Turbo, about 32.5 GB.
Video needs a separate engine installation and accepted model terms; see [Model setup](docs/MODEL_SETUP.md).
Voice uses a separate environment prepared on first use, so its first request includes dependency setup and model loading.

To explore the interface without loading or downloading models:

```sh
uv run studio --stub
```

The stub simulates progress, returns placeholder images and a test tone for Voice, and returns metadata instead of an encoded video.

## Three workspaces

| Workspace | Default model | What you can do |
|---|---|---|
| **Image** | Qwen-Image-2.1-Turbo | Generate, edit with image references, mark regions, compare before and after, and prepare multiple outputs. |
| **Video** | LTX-2.5 | Generate from text, image keyframes, and an optional audio track; edit clips with model-specific effects. |
| **Voice** | Drama-3 | Generate speech with inline delivery cues or clone a reference voice using its transcript. Select AuK for voice design and instruction edits. |

Each workspace has templates, model-specific controls, preview actions, and a gallery.
Send references between workspaces: an image can become a Video keyframe, and a selected Voice range can become its audio track.
Voice previews include a waveform, draggable selection handles, and playback speed control.

**Prompt assistance.** Image Rewrite uses dedicated Qwen prompt models. Video Rewrite uses LTX’s native Gemma enhancer,
which also runs automatically before generation. With image references, enhancement reads the first image.
An unchanged rewritten prompt and reference skip duplicate enhancement within the server session.

**Shared operations.** One operation runs at a time. API jobs select the active workspace in the UI,
lock conflicting controls, and show the same progress and pending gallery item across tabs.
Cancel keeps finished batch items and preserves inputs for retrying.

**Local storage.** With **Keep in this browser** enabled, drafts, references, and saved gallery media survive reloads.
Turning it off clears browser storage. Separately, the server retains recent API results in memory for up to one hour,
32 operations, or 256 MiB, whichever limit comes first. Restarting clears server history.
Download anything you want to keep outside the browser.

## API for scripts and agents

Open **http://127.0.0.1:8765/api/docs** for the rendered OpenAPI reference with named request examples.
Read [API.md](API.md) for model differences, media encoding, batch recipes, and official prompting guides.
The raw specification is available at `/api/v1/openapi.json`.

Discover the selected models and their controls before submitting work:

```sh
curl -sS http://127.0.0.1:8765/api/v1/studio
```

Start a reproducible image operation:

```sh
curl -sS http://127.0.0.1:8765/api/v1/operations \
  -H 'Content-Type: application/json' \
  -d '{"kind":"image","backend":"qwen21_turbo","prompt":"A red pear on a wooden table, soft window light.","width":768,"height":768,"seed":7}'
```

The response supplies a `status_url`. Poll it until the operation finishes, then fetch its `result_url`.
`GET /api/v1/state` exposes shared activity; the operation’s cancel endpoint stops it.
A conflicting request returns `409` while another operation is active.

Image, Video, and Voice support ordered batches of up to **16 items** through `/api/v1/operations`.
One reservation covers the batch. The engine reuses models and conditioning where supported;
a batch does not imply that all items render in parallel or that every workload becomes faster.

## Models and configuration

Default startup offers one model per workspace. Enable the model selectors with:

```sh
uv run studio --all-backends
```

| Workspace | Optional models | Setup |
|---|---|---|
| Image | Qwen-Image-2.1, Viggle Turbo, FLUX.2 klein-base-9B | Some models require manually downloaded weights or adapters. |
| Video | LTX-2.3 | Optional and disabled by default; restore its separate weights before use. |
| Voice | AuK, AuK Flash | Shared pinned weights, downloaded on first use. |

[Model setup](docs/MODEL_SETUP.md) contains download recipes, engine versions, reference limits, and model-specific behavior.
[studio.toml](studio.toml) controls model paths, defaults, and the visible models in each workspace.
Image models use full precision by default. Video and Voice use the configured eight-bit checkpoints.
Video **Fast mode**, in Advanced and the API, uses float16 transformer computation with the same weights;
it can change generated details. See [Fast mode](API.md#video-fast-mode) for scope and tradeoffs.

| Command | Purpose |
|---|---|
| `uv run studio --port 9000` | Use another port. Browser storage is separate for each address and port. |
| `uv run studio --backend qwen21` | Open on the full Qwen Image model. |
| `uv run studio -q 8` | Quantize the opening Image model to eight bits. |
| `uv run studio --config path/to/studio.toml` | Use another configuration file. |
| `uv run studio --stub --all-backends` | Explore all model forms without GPU work. |

## Why it looks like this

Models share one memory slot, and workspace switches release inactive model memory.
Image batches retain their engine; Video selects a reuse policy by geometry, length, and memory budget.
Voice batches retain their model and reference caches. Memory residency, prompt preparation, and caching
have been measured separately; gains depend on the model, workload, and machine pressure.

[Design decisions and measurements](docs/DESIGN_DECISIONS.md) records the comparisons, unchanged-output checks,
regressions, and cases where batching offered little gain.
[Prompt-aid verdicts](studio/l3_interface_adapters/gateways/PROMPTS.md) document model-specific templates and Looks.

## Development

The application uses Clean Architecture with separate model gateways and shared use cases for the UI and API.
See [ARCHITECTURE.md](studio/ARCHITECTURE.md) for the layers, import boundaries, and backend integration steps.

```sh
uv run pytest
uv run prek run --all-files
```

The CPU suite enforces 100% statement and branch coverage for `studio/`.
Browser checks live in `tests/e2e/`; use a fresh stub server for UI work.
Tests marked `live` require installed weights and an available GPU.
Local experiment artifacts and research notes stay outside the checkout.

## Licenses

The weights keep their own licenses. Qwen-Image-2.1 is under the Qwen Research License, which allows research use only, and Viggle's adapter for it is under the same license. FLUX.2 klein-base-9B is under the FLUX Non-Commercial License. Check them before you use any output commercially.

AuK's own code, diffusion weights, and audio decoder use the [MIT license](https://github.com/Tencent-Hunyuan/AuK/blob/main/LICENSE).
The bundled Thinker derives from Qwen2.5-Omni-3B and carries the Qwen Research license.
The [distributed weight card](https://huggingface.co/smcleod/AuK-MLX-8bit) declares the combined license as `mit-plus-qwen-research`.
The complete Voice stack therefore retains that research license restriction. Do not treat it as entirely MIT-licensed.

Drama-3 weights use the [Fish Audio Community License 1.0](https://huggingface.co/mlx-community/fish-audio-drama-3-8bit/blob/fedc7cc92bab5a180709cbaae6208d10b390bb97/LICENSE). Its community commercial eligibility and hosted-service terms differ from the MLX Audio code license.
