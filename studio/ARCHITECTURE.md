# studio architecture

studio is the web page and its server. The page never knows which model runs. It reads what the backend supports from a capabilities record, and it hides or disables the rest.

## Layers

Each layer imports only the layers inside it. `.importlinter` enforces this, and `uv run lint-imports` checks it.

| Layer | Directory | What it holds |
|---|---|---|
| 1. Entities | `l1_entities/` | The job, the result, the progress, the errors, and the capabilities record: modes, params, Looks, templates, estimate |
| 2. Use cases | `l2_use_cases/` | Run an image or video, describe the studio, switch either backend, release model memory, rewrite a prompt, and read progress. `boundaries/` holds their ports. |
| 3. Interface adapters | `l3_interface_adapters/` | The form and video controllers, the HTML presenter, model gateways, in-memory stores, and the GPU thread for MLX calls |
| 4. Frameworks and drivers | `l4_frameworks_and_drivers/` | The HTTP server, local LTX process runner, config file, page, and `main.py`, which wires everything |

The entities and use cases import no engine: no mlx, mflux, PIL, http or subprocess. The backend adapters do not import each other; what two of them share sits next to them in `gateways/`.

The engine choice is made in layer 4, from the probe in `engines.py`, not in a gateway. An engine that only one platform has is a decision at the top, not a branch inside the adapter. Engine code that already branches is not converted; `gateways/qwen21/PORTABILITY.md` records what a port would need.

The image and video workspaces have separate backend catalogs and selections. They share one model-memory slot and one non-queueing lock. The server starts without loading weights. A model loads only when its run starts. Selecting another model releases the current one but does not load the new one. Leaving a workspace releases its model. The LTX pipeline runs in a child process, which releases its weights when it exits. A prompt rewrite takes the same lock and releases its weights when it ends.

Names follow the role. A gateway ends in `_gateway.py` and its class in `Gateway`. A use case ends in `_use_case.py` and `UseCase`. Controllers and presenters do the same. Entities and the records passed between layers have no suffix.

## One request

1. The HTTP server hands the form to `FormController`.
2. The controller turns it into a `RunImageRequest` and calls `RunImageUseCase`.
3. The use case checks the form against the selected image backend's `ModeSpec` and claims the shared model-memory slot.
4. The use case calls `ImageBackendGateway.run`, which loads only the engine needed for that mode.
5. The gateway runs the engine on the GPU thread and returns PNG bytes.
6. The use case returns a response record. The HTTP server hands it to `HtmlPresenter`, which writes the HTML fragment.

## One video request

1. The page sends the selected video backend, prompt, output settings, and still keyframes as JSON to `/video/generate`.
2. `VideoController` reads that backend's `VideoCapabilities`, checks the request, and decodes stills to PNG bytes.
3. `RunVideoUseCase` takes the shared lock and claims the shared model-memory slot.
4. The selected `VideoBackendGateway` runs the model. `Ltx25BackendGateway` calls the injected runner, which starts the official Python pipeline.
5. The LTX runner downloads missing official components on first use, writes keyframes to a temporary folder, and starts `ltx_pipelines.distilled`.
6. The page puts MP4 output in the video gallery. The stub returns settings only and creates no fake video bytes.

The model selector follows the active workspace. Each workspace keeps its own selected backend and capabilities. Video settings come from `VideoCapabilities`, so a backend declares its supported shapes and default, frame limits and step, duration presets and default, frame rate, seed range, reference limit, and reference strength range and step. The Video source panel lives beside its prompt in the right sidebar. It keeps imported clips separate from image keyframes. The Video gallery holds generated output only. A frame from an imported or generated clip can move to Image or become a Video keyframe. The source clip itself is not a video-conditioning input.

A batch is a chain of requests, one per image. Progress is a poll of `/progress`. A rewrite is one request of its own, and its phase is a poll of `/rewrite/state`: the page offers a cancel only while the model is writing, because a stop cannot land during the load.

## Add a backend

1. Write the backend capability record. Image backends use `Capabilities`; video backends use `VideoCapabilities`.
2. Write a gateway that implements the matching port. Image gateways implement `ImageBackendGateway`; video gateways implement `VideoBackendGateway`.
3. Add a builder to `BACKENDS` or `VIDEO_BACKENDS`. Add the model to the matching default and visible lists in `studio.toml`.
4. Keep model loading lazy. A run loads the needed weights. Switching models releases the old backend without preloading the new one.
5. Add gateway tests at the mirrored path under `tests/`. Mock the engine for unit tests, so they run without weights.
6. Run the relevant workspace with the stub, then verify the real backend when its model is available.

The image form knows two mode ids, `generate` and `edit`, and the params `size`, `resolution`, `steps`, `guidance`, `cfg`, `strength` and `negative`. The video form has its own prompt, frame-grid duration, shape, source panel, timeline, and output gallery. Image and video references use separate request records. All image, video, and rewrite work uses the shared memory lock.

An image edit may carry a marked region. The page appends it as the last image of the run, and replaces the prompt's `[the region you marked]` with that image's number. Only a mode that declares `region_marking` is offered the tool. A backend declares the modes it supports. A new kind of image parameter needs a control in `web/page.html`.

## The page

`web/page.html` is one file, 921 lines as the refactor stands, of which 658 are its inline
script, and the rest of its logic lives in modules under `web/lib/` and `web/components/`,
which the static route serves. `web/PAGE-REFACTOR.md` is the design for taking it apart into Lit components, light DOM, with no bundler. Read it before you change how the page is built. It also lists the ids, roles and attributes that the e2e checks pin, and those must not move: `tests/e2e/verify_ui.py` is the executable version of that contract.

## Tests

- The tree under `tests/` mirrors the tree under `studio/`. The module `studio/a/b/c.py` is tested by `tests/a/b/c/test_c.py`. A shared helper lives in `tests/support/` and mirrors no module. `tests/e2e/` holds the browser checks and mirrors nothing.
- Every statement and every branch in `studio/` runs under `uv run pytest`, and that run fails when either number drops. A new module needs its mirrored test file, or the gate stops the commit.
- Mock the engines. Every engine is imported inside the function that needs it, so `tests/support/heavy.py` puts a stub in `sys.modules` and the real import never runs. No unit test loads a model, reads the weights, or touches the GPU.
- `prek install` once per clone. Each commit then runs ruff, ty, import-linter and a secret scan, and checks the message against Conventional Commits.
- `uv run pytest` runs the unit and gateway tests. They need no model.
- `uv run pytest -m live` loads real weights.
- `tests/e2e/` holds browser checks. Each script names how to run it in its first lines. `verify_capabilities.py` needs no GPU. `verify_page.py`, `verify_batch.py` and `verify_backends.py` run real models against a running server. `verify_storage.py` checks the images the browser keeps, and the stub is enough for it. `verify_ui.py` checks the controls: the mode, the size chips, the Look rows, the Advanced panel, a run, a cancel, and the rewrite. It binds to roles, accessible names and the ids the page publishes, never to a decorative class, so a change to how the page is drawn does not move it.
