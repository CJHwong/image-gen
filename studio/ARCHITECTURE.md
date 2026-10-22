# studio architecture

studio is the web page and its server. The page never knows which model runs. It reads what the backend supports from a capabilities record, and it hides or disables the rest.

## Layers

Each layer imports only the layers inside it. `.importlinter` enforces this, and `uv run lint-imports` checks it.

| Layer | Directory | What it holds |
|---|---|---|
| 1. Entities | `l1_entities/` | The job, the result, the progress, the errors, and the capabilities record: modes, params, Looks, templates, estimate |
| 2. Use cases | `l2_use_cases/` | Run image, video, or Voice jobs, describe the studio, switch backends, release model memory, rewrite prompts, and read progress. `boundaries/` holds their ports. |
| 3. Interface adapters | `l3_interface_adapters/` | The form and video controllers, the HTML presenter, the JSON API, model gateways, including the MLX video pack under `gateways/mlx_video`, in-memory stores, and the GPU thread for MLX calls |
| 4. Frameworks and drivers | `l4_frameworks_and_drivers/` | The HTTP server, local LTX process runner, config file, page, and `main.py`, which wires everything |

The entities and use cases import no engine: no mlx, mflux, PIL, http or subprocess. The backend adapters do not import each other; what two of them share sits next to them in `gateways/`.

The engine choice is made in layer 4, from the probe in `engines.py`, not in a gateway. An engine that only one platform has is a decision at the top, not a branch inside the adapter. Engine code that already branches is not converted; `gateways/qwen21/PORTABILITY.md` records what a port would need. A checkpoint's sampling schedule is wired the same way: layer 4 registers the official Turbo checkpoint's own sigma table, which lives beside the backends in `gateways/qwen21_turbo_schedule.py` because a backend may not import another backend.

Image, Video, and Voice have separate backend catalogs and selections. Voice offers Drama-3 by default, AuK, and AuK Flash. They share one model-memory slot and one non-queueing lock. The server starts without loading weights. A model loads only when its run starts. Selecting another model releases the current one but does not load the new one. Leaving a workspace releases its model. The LTX pipelines run in a child process, which releases its weights when it exits. The MLX q8 packs run the same way through their port. A prompt rewrite takes the same lock and releases its weights when it ends.

Names follow the role. A gateway ends in `_gateway.py` and its class in `Gateway`. A use case ends in `_use_case.py` and `UseCase`. Controllers and presenters do the same. Entities and the records passed between layers have no suffix.

## One request

1. The HTTP server hands the form to `FormController`.
2. The controller turns it into a `RunImageRequest` and calls `RunImageUseCase`.
3. The use case checks the form against the selected image backend's `ModeSpec` and claims the shared model-memory slot.
4. The use case calls `ImageBackendGateway.run`, which loads only the engine needed for that mode.
5. The gateway runs the engine on the GPU thread and returns PNG bytes.
6. The use case returns a response record. The HTTP server hands it to `HtmlPresenter`, which writes the HTML fragment.

## One video request

1. The page sends a unique request ID, the selected video backend, prompt, output settings, and still references with target frames as JSON to `/video/generate`.
2. `VideoController` reads that backend's `VideoCapabilities`, checks the request, and decodes stills to PNG bytes.
3. `RunVideoUseCase` takes the shared lock and claims the shared model-memory slot.
4. The selected `VideoBackendGateway` runs the model. `Ltx25BackendGateway` calls the injected runner, which starts the official Python pipeline.
5. The LTX runner downloads missing official components on first use, writes keyframes to a temporary folder, and starts `ltx_pipelines.distilled`. A cancel request terminates the child process.
6. The page puts MP4 output in the video gallery. When **Keep in this browser** is on, IndexedDB stores the MP4, thumbnail, and generation details. The stub returns settings only and creates no fake video bytes.

The model selector follows the active workspace. Each workspace keeps its own selected backend and capabilities. Video settings come from `VideoCapabilities`, so a backend declares its supported shapes and default, frame limits and step, duration presets and default, frame rate, seed range, reference limit, and reference strength range and step. The Video source panel lives beside its prompt in the right sidebar. It keeps imported clips separate from image keyframes. The Video gallery holds generated output only. A frame from an imported or generated clip can move to Image or become a Video keyframe. The source clip itself is not a video-conditioning input.

The image-count control uses a legacy chain of requests, one per image. Explicit API batches use one request and one reservation. Image progress is a poll of `/progress`. Video progress is a poll of `/video/progress`, which includes the active request ID. Every tab also polls `/api/v1/state` from startup and follows API or other-tab operations. It sends cancellation to `/video/cancel` with the same ID. The legacy route stops only that matching run. The shared operation route cancels by operation ID. The MLX runner combines sampler steps across stages into one count. It ignores weight-loading counters. The page keeps progress below 100% until the clip is ready. After denoising, it shows Finishing the clip while decoding and saving continue. A video cancel terminates the LTX child and releases the shared lock after it exits. The timeline keeps source clips and reference keyframes. A rewrite is one request of its own, and its phase is a poll of `/rewrite/state`: the page offers a cancel only while the model is writing, because a stop cannot land during the load.

## One Voice request

1. The Voice component sends a script or edit instruction to `/voice/operations` with its browser identities.
2. Public clients use `/api/v1/operations` with `kind: "voice"` and the same validated payload.
3. `VoiceController` checks the selected Voice model capabilities and converts reference WAV bytes into a `SpeechJob`.
4. `RunVoiceUseCase` takes the shared lock, checks the selected backend, and claims its model-memory slot.
5. The selected Voice gateway uses one resident child with its pinned environment and weights.
6. AuK batches prepare a neutral sample per shared voice and clone it for matching items. Drama-3 keeps its model and explicit reference conditioning resident.
7. Each completed item enters the operation manifest immediately. Cancellation keeps completed items.
8. The page generates one continuous clip and clears its own submitted draft after success. Explicit API items support independent clips.

Voice uses `voice_capabilities.py` and `VoiceBackendGateway`. Its records do not import Image or Video adapters.
A resident Voice child exits after a model switch, memory release, or another workspace claims the model slot.
Voice capabilities declare a model-specific default mode, reference sample rate and duration limit. Required text parameters include Drama-3 reference transcripts. Templates explicitly target the spoken text or the AuK voice description. The page reconciles unsupported modes and stale template settings when a model changes.
Drama-3 decodes its codec incrementally and joins all audio at native rate. It rejects capped generation and missing internal text chunks; unknown generation length stays indeterminate in the shared progress state.
The Voice capabilities declare the first-use download policy and pinned weight identity.

## Engine reuse in batches

Image batches hold the engine lock for all items. Official Qwen Turbo prepares unique prompt embeddings before denoising releases the encoder.
Eligible MLX video batches encode prompts together and free Gemma. The runner keeps sizes at or below 768×768 sequential and chooses cleanup or decoder-offload profiles by geometry, clip length, and measured memory budget. Only one clip is sampled at a time; the item count does not multiply activation memory. Validated item-start events reset each clip’s timeout while initial loading remains bounded.
Unsupported video settings use sequential calls within the same operation. The eligibility check stays beside the video runner.
LTX-2.5 declares optional Fast mode in its capabilities. The controller validates a boolean on
each job and one shared choice per batch. The runner passes float16 or default float32 computation
to each render child's environment without mutating the parent. Fast mode enables residency only
for the measured enhanced homogeneous 768×768×121 text-only batch on at least 64 GiB; conditioned
jobs retain their existing profiles. The page persists the local choice and temporarily shows an
observed operation's choice while controls are locked, then restores the local choice.
Voice batches retain the selected engine. AuK reuses a neutral designed voice; Drama-3 reuses encoded reference audio and prompt-prefix caches. Every workspace still runs only one GPU job at a time.
See the measured comparisons in the README before extending an optimization to another engine or output shape.

## Add a backend

1. Write the backend capability record. Image backends use `Capabilities`; video backends use `VideoCapabilities`.
2. Write a gateway that implements the matching port. Image gateways implement `ImageBackendGateway`; video gateways implement `VideoBackendGateway`.
3. Add a builder to `BACKENDS` or `VIDEO_BACKENDS`. Add the model to the matching default and visible lists in `studio.toml`.
4. Keep model loading lazy. A run loads the needed weights. Switching models releases the old backend without preloading the new one.
5. Add gateway tests at the mirrored path under `tests/`. Mock the engine for unit tests, so they run without weights.
6. Run the relevant workspace with the stub, then verify the real backend when its model is available.

The image form knows two mode ids, `generate` and `edit`, and the params `size`, `resolution`, `steps`, `guidance`, `cfg`, `strength` and `negative`. The video form has its own prompt, frame-grid duration, shape, source panel, timeline, and output gallery. Image and video references use separate request records. All Image, Video, Voice, and rewrite work uses the shared memory lock.

An image edit may carry a marked region. The page appends it as the last image of the run, and replaces the prompt's `[the region you marked]` with that image's number. Only a mode that declares `region_marking` is offered the tool. A backend declares the modes it supports. A new kind of image parameter needs a control in `web/page.html`.

## The page

`web/page.html` holds the layout and workspace wiring. The other page logic lives in modules under `web/lib/` and `web/components/`,
which the static route serves. `web/PAGE-REFACTOR.md` is the design for taking it apart into Lit components, light DOM, with no bundler. Read it before you change how the page is built. It also lists the ids, roles and attributes that the e2e checks pin, and those must not move: `tests/e2e/verify_ui.py` is the executable version of that contract.

## Tests

- The tree under `tests/` mirrors the tree under `studio/`. The module `studio/a/b/c.py` is tested by `tests/a/b/c/test_c.py`. A shared helper lives in `tests/support/` and mirrors no module. `tests/e2e/` holds the browser checks and mirrors nothing.
- Every statement and every branch in `studio/` runs under `uv run pytest`, and that run fails when either number drops. A new module needs its mirrored test file, or the gate stops the commit.
- Mock the engines. Every engine is imported inside the function that needs it, so `tests/support/heavy.py` puts a stub in `sys.modules` and the real import never runs. No unit test loads a model, reads the weights, or touches the GPU.
- `prek install` once per clone. Each commit then runs ruff, ty, import-linter and a secret scan, and checks the message against Conventional Commits.
- `uv run pytest` runs the unit and gateway tests. They need no model.
- `uv run pytest -m live` loads real weights.
- `tests/e2e/` holds browser checks. Each script names how to run it in its first lines. `verify_capabilities.py` needs no GPU. `verify_page.py`, `verify_batch.py` and `verify_backends.py` run real models against a running server. `verify_storage.py` checks the images the browser keeps, and the stub is enough for it. `verify_ui.py` checks the controls: the mode, the size chips, the Look rows, the Advanced panel, a run, a cancel, and the rewrite. It binds to roles, accessible names and the ids the page publishes, never to a decorative class, so a change to how the page is drawn does not move it.

## Shared operations

The JSON adapter records operations for browser and API requests. One reservation covers a complete Image, Video, or Voice batch, or one rewrite.
The HTTP driver creates a worker thread only for the optional asynchronous route. Existing synchronous routes keep their response formats.
The operation store retains bounded metadata and results. It keeps completed items after cancellation or failure. Active batches expose their manifest and completed item URLs.
A browser batch carries its operation ID in each continuation. A 30-second lease applies only between requests.
An active engine call never expires through that lease. API batches need no continuation requests.
The page polls shared state, imports results with stable identities, and preserves unsent prompts during model changes.
Browser libraries and presentation preferences stay in IndexedDB and local storage. See [API.md](../API.md) for the public contract.

The UI clips overlong Drama-3 reference picks to the first fifteen seconds at the native reference rate. It clears copied transcripts after an actual trim and retries normalization against changed capabilities before committing a pending decode. References restored while globally locked are reconciled on unlock. API clients trim explicitly, so the reference transcript can match the chosen excerpt.

Every LTX Generate request enables the engine's separate Gemma-3 prompt-enhancement pass. Normal generation uses the native CLI flag; audio-conditioned generation calls the same helper before the a2v pipeline, because the pinned audio parser lacks that flag. This pass finishes and frees its model before video loading. It is independent of Studio Rewrite, and Edit adapter prompts are unchanged. Eligible Generate batches run enhancement in one separate child before the video child. Auto keeps per-item execution for the measured enhanced two-item 1920×1088, 17-frame, 24-fps text regression; the guard does not extend to another item count, duration or conditioning mode. It loads Gemma once, preserves each item’s seed and native enhancement strategy, writes effective prompts and resolved random seeds back to a temporary manifest, then exits. Video encoding therefore sees enhanced prompts, without a second enhancement pass, and the enhancer process cannot hold accelerator allocations while video loads. The existing geometry/memory planner selects video reuse; otherwise the video child renders sequentially with cleanup between clips. Mixed Edit batches retain per-item execution. The whole enhancement phase has one hour to finish; validated render-start events reset the per-clip timeout. Cancellation stops the currently owned child and keeps clips already published.
