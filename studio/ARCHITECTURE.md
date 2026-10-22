# studio architecture

studio is the web page and its server. The page never knows which model runs. It reads what the backend supports from a capabilities record, and it hides or disables the rest.

## Layers

Each layer imports only the layers inside it. `.importlinter` enforces this, and `uv run lint-imports` checks it.

| Layer | Directory | What it holds |
|---|---|---|
| 1. Entities | `l1_entities/` | The job, the result, the progress, the errors, and the capabilities record: modes, params, Looks, templates, estimate |
| 2. Use cases | `l2_use_cases/` | Run image, video, or Voice jobs, describe the studio, switch backends, release model memory, rewrite prompts, and read progress. `boundaries/` holds their ports. |
| 3. Interface adapters | `l3_interface_adapters/` | The form and video controllers, the HTML presenter, the JSON API, model gateways, grouped under `gateways/image`, `gateways/video`, and `gateways/audio`, in-memory stores, and the GPU thread for MLX calls |
| 4. Frameworks and drivers | `l4_frameworks_and_drivers/` | The HTTP server, generic subprocess driver, config file, platform probe, page, and `main.py`, which wires everything |

The entities and use cases import no engine: no mlx, mflux, PIL, http or subprocess. The backend adapters do not import each other; what two of them share sits next to them in `gateways/`.

The engine choice is made in layer 4, from the probe in `engines.py`, not in a gateway. An engine that only one platform has is a decision at the top, not a branch inside the adapter. Engine code that already branches is not converted; `gateways/image/qwen21/PORTABILITY.md` records what a port would need. A checkpoint's sampling schedule is wired the same way: layer 4 registers the official Turbo checkpoint's own sigma table, which lives beside the backends in `gateways/image/shared/qwen21_turbo_schedule.py` because a backend may not import another backend.

Image, Video, and Voice have separate backend catalogs and selections. Voice offers Drama-3 by default, AuK, and AuK Flash. They share one model-memory slot and one non-queueing lock. The server starts without loading weights. A model loads only when its run starts. Selecting another model releases the current one but does not load the new one. Leaving a workspace releases its model. The LTX pipelines run in a child process, which releases its weights when it exits. The MLX q8 packs run the same way through their port. A prompt rewrite takes the same lock and releases its weights when it ends.

Names follow the role. A gateway ends in `_gateway.py` and its class in `Gateway`. A use case ends in `_use_case.py` and `UseCase`. Controllers and presenters do the same. Entities and the records passed between layers have no suffix.

## Model gateway ownership

Every generation model has one concrete gateway in its own media/model package:

```text
gateways/
  image/{qwen21,qwen21_turbo,viggle_turbo,flux2}/
  video/{ltx25,ltx23}/
  audio/{drama3,auk,auk_flash}/
```

Each package implements its media boundary. AuK and AuK Flash have separate gateways;
LTX-2.3 and LTX-2.5 do too. A gateway fixes its model identity rather than selecting
between models at runtime. Existing public backend IDs remain stable.
Shared engine helpers live in `image/qwen_runtime`, `image/shared`, `video/shared`,
`video/ltx_runtime`, and `audio/auk_runtime`. These packages are implementation helpers, not additional
model gateways. `.importlinter` forbids imports between all nine model packages.
Layer 4 constructs the model-specific gateway and injects its engine dependencies.
LTX command construction, batching and memory profiles, sampler progress interpretation,
and engine child scripts live in `video/ltx_runtime`. Gemma instructions, enhancement,
image handling and the Rewrite cache live in `video/gemma3`. Neither imports layer 4.
`SubprocessRunner` in layer 4 owns only process I/O, environment scoping, timeouts and
termination; the composition root injects its callable into the adapters. Model-specific
failure messages and interpretation stay in `video/shared`. A separate import contract
prevents framework drivers from reaching model gateways outside the composition root.
Tests mirror the same media/model paths. Add a new model as a new package, including
when it shares an engine or publisher with an existing model.

## Boundaries and composition

The responsibility split follows the [Clean Architecture examples](https://github.com/CJHwong/py-clean-architecture-examples)
and their [dependency rule](https://github.com/CJHwong/py-clean-architecture-examples/blob/main/doc/principles.md).
Dependencies point inward; application policy uses ports, and the composition root supplies concrete adapters.

- `PrepareBatchUseCase` owns batch envelope policy: item limits, inherited defaults, one model and
  one result per item. The HTTP adapter does not define a second batch limit.
- `CompleteOperationUseCase` owns the common success/failure path. Its only dependency is the
  `OperationGateway` port. It accepts and returns plain operation records, retaining the prepared result
  and recording failures before propagating them. Transport serialization happens in the adapter.
- `InMemoryOperationGateway` implements atomic reservations, continuation ownership, cancellation,
  and bounded result storage. Its locks and retention bookkeeping stay outside the use cases.
  It stores a result-retention flag, not HTTP routes. `OperationMissing` is an inner error;
  the HTTP driver translates it to a 404.
- `JsonApi` adapts the public JSON and legacy form entry points to the same controllers. It receives
  its operation store, completion use case, and batch use case; it constructs none of them.
  `api/request_mapper.py` converts transport values. `presenters/json_presenter.py` builds response
  documents, including operation URLs, without importing controllers or storage implementations.
- `main.py` is the composition root for every workspace. It builds the concrete operation store
  once and supplies that same instance to the JSON adapter and completion use case. The shared
  progress adapters observe cancellation from that same operation state.

`.importlinter` enforces the four layers and adapter isolation. API adapters cannot import concrete
storage or model gateways. Controllers, presenters and gateways cannot import the API adapter.
A change to an endpoint's route or JSON shape should not require a change to a model gateway or use case.

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
4. The selected `VideoBackendGateway` runs the model. `Ltx25BackendGateway` or `Ltx23BackendGateway` calls its injected MLX runner.
5. The MLX runner resolves the selected model pack, writes conditioning inputs to a temporary folder, and starts the pinned pipeline child. A cancel request terminates that owned child process.
6. The page puts MP4 output in the video gallery. When **Keep in this browser** is on, IndexedDB stores the MP4, thumbnail, and generation details. The stub returns settings only and creates no fake video bytes.

The model selector follows the active workspace. Each workspace keeps its own selected backend and capabilities. Video settings come from `VideoCapabilities`, so a backend declares its supported shapes and default, frame limits and step, duration presets and default, frame rate, seed range, reference limit, and reference strength range and step. The Video source panel lives beside its prompt in the right sidebar. It keeps imported clips separate from image keyframes. The Video gallery holds generated output only. A frame from an imported or generated clip can move to Image or become a Video keyframe. The source clip itself is not a video-conditioning input.

The image-count control expands multiple results into explicit items and submits one asynchronous prepared batch through `/image/operations`, the UI identity wrapper around the same operation API. Per-reference edits cycle references and their own instructions in item order, with one exact decimal seed sequence. The server emits the batch item limit; the count menu limits results per reference so the total fits the same API envelope. Shared polling imports completed items incrementally, including in the submitting tab and after reload. The originating tab decorates results with its Look and reference comparison metadata; precision is retained on the operation for reloads. Cancellation or a failed submission restores consumed inputs. Single-image forms retain their existing htmx transport. Explicit API batches use the same batch use case and one reservation. Image progress is a poll of `/progress`. Video progress is a poll of `/video/progress`, which includes the active request ID. Every tab also polls `/api/v1/state` from startup and follows API or other-tab operations. It sends cancellation to `/video/cancel` with the same ID. The legacy route stops only that matching run. The shared operation route cancels by operation ID. The MLX runner combines sampler steps across stages into one count. It ignores weight-loading counters. The page keeps progress below 100% until the clip is ready. After denoising, it shows Finishing the clip while decoding and saving continue. A video cancel terminates the LTX child and releases the shared lock after it exits. The timeline keeps source clips and reference keyframes. A rewrite is one request of its own, and its phase is a poll of `/rewrite/state`: the page offers a cancel only while the model is writing, because a stop cannot land during the load.

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

The shared header guide is owned by `web/components/studio-guide.js`, independently of any
preview renderer. Its overlay lives in the shared workspace grid, so preview redraws cannot
remove it or hide it inside the Image stage. The page supplies the current workspace and model;
Voice help distinguishes Drama-3 from AuK. Workspace or model changes close stale guidance.
The guide retains the existing toggle, sheet, keyboard and focus contracts and links to `/api/docs`.

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

Every LTX Generate request enables the engine's separate Gemma-3 prompt-enhancement pass. Text generation uses the native CLI flag; image-conditioned generation uses a Studio child to forward `args.images[0].path` into Gemma’s vision tower through `mlx-vlm`. Audio-conditioned generation calls the same enhancement helper before the a2v pipeline, because the pinned audio parser lacks that flag. This pass finishes and frees its model before video loading. Video Rewrite now uses the same native Gemma 3 strategies through `video/gemma3/Gemma3PromptRewriterGateway`, injected separately from the Image rewriter. A bounded, session-local Gemma adapter cache remembers 128 exact enhanced outputs and the first reference PNG digest (or no reference). A subsequent single or batched Generate with the same prompt and first reference image skips duplicate enhancement; changed text or conditioning triggers enhancement again. Edit adapter prompts are unchanged. Studio’s image-aware driver retains the engine’s native I2V instructions and sampling settings, but uses `mlx-vlm` to read the first attached reference. Later keyframes remain generator inputs. Eligible Generate batches run enhancement in one separate child before the video child. Auto keeps per-item execution for the measured enhanced two-item 1920×1088, 17-frame, 24-fps text regression; the guard does not extend to another item count, duration or conditioning mode. It groups prompts by checkpoint and text/image strategy, holds only one enhancement model at a time, and frees each group before loading the next. It preserves each item’s seed and native enhancement strategy, writes effective prompts and resolved random seeds back to a temporary manifest, then exits. Video encoding therefore sees enhanced prompts, without a second enhancement pass, and the enhancer process cannot hold accelerator allocations while video loads. The existing geometry/memory planner selects video reuse; otherwise the video child renders sequentially with cleanup between clips. Mixed Edit batches retain per-item execution. The whole enhancement phase has one hour to finish; validated render-start events reset the per-clip timeout. Cancellation stops the currently owned child and keeps clips already published.

Inactive workspace controls are disabled fieldsets. Hidden Voice or Video numeric constraints therefore cannot prevent native Image form submission. Voice validates supported numeric limits in its own Generate reason before submitting; Drama-3 remains at a 2048 default and a supported range of 64–2048.

Startup uses the same model-list policy for Image, Video, and Voice. The shipping configuration offers one default per workspace; `--all-backends` passes each registry as its workspace visibility override. Optional models are constructed lazily and still require installed weights before use. Custom visible lists can expose a subset.

Drama-3 bounds its active-generation wired-memory limit by MLX’s recommended working set and 75% of physical RAM. It synchronizes and restores the previous process limit on success or failure; idle models remain reclaimable. Cancellation terminates the child. Sampling and precision are unchanged.

The shared operation bar is the sole global status readout for Image, Video, Voice, and Rewrite. It occupies an explicit grid row below the header and remains visible on mobile. It separates phase, model/item, elapsed time, and cancellation. Unknown totals remain indeterminate; active percentages stay below 100%. The Image preview reads aggregate operation counters independently of the legacy per-image poll used to learn timing. Per-operation display progress never decreases, including item transitions and temporary missing counters.

The composition root injects the bounded active-memory scope into the official Qwen Turbo gateway. The scope covers Generate, Edit, and batch prompt preparation, synchronizes outstanding MLX work, and restores the prior wired limit in nested cleanup even if synchronization fails. Other Image backends keep their existing memory policy. Both Image Cancel controls arm the native input-restoration lifecycle for the submitted draft. Shared-bar cancellation always targets the displayed operation ID; draft matching prevents a stale snapshot or an API request from restoring a different native draft.


Local experiment evidence and research notes live outside the checkout. The repository
keeps product setup, API documentation and measured conclusions, rather than raw reports.
The `reports/` and `research_notes/` ignore rules prevent accidental reintroduction.
