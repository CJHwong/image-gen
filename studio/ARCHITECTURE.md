# studio architecture

studio is the web page and its server. The page never knows which model runs. It reads what the backend supports from a capabilities record, and it hides or disables the rest.

## Layers

Each layer imports only the layers inside it. `.importlinter` enforces this, and `uv run lint-imports` checks it.

| Layer | Directory | What it holds |
|---|---|---|
| 1. Entities | `l1_entities/` | The job, the result, the progress, the errors, and the capabilities record: modes, params, Looks, templates, estimate |
| 2. Use cases | `l2_use_cases/` | Run an image, describe the studio, switch the backend, prepare, rewrite a prompt, and cancel or read the progress of either job. `boundaries/` holds the ports they call. |
| 3. Interface adapters | `l3_interface_adapters/` | The form controller, the HTML presenter, and the gateways: one per backend, the in-memory stores, and the GPU thread that every MLX call must run on |
| 4. Frameworks and drivers | `l4_frameworks_and_drivers/` | The HTTP server, the config file, the page, and `main.py`, which wires everything |

The entities and use cases import no engine: no mlx, mflux, PIL, http or subprocess. The backend adapters do not import each other; what two of them share sits next to them in `gateways/`.

The engine choice is made in layer 4, from the probe in `engines.py`, not in a gateway. An engine that only one platform has is a decision at the top, not a branch inside the adapter. Engine code that already branches is not converted; `gateways/qwen21/PORTABILITY.md` records what a port would need.

Names follow the role. A gateway ends in `_gateway.py` and its class in `Gateway`. A use case ends in `_use_case.py` and `UseCase`. Controllers and presenters do the same. Entities and the records passed between layers have no suffix.

## One request

1. The HTTP server hands the form to `FormController`.
2. The controller turns it into a `RunImageRequest` and calls `RunImageUseCase`.
3. The use case checks the form against the active backend's `ModeSpec`, then calls `ImageBackendGateway.run`.
4. The gateway runs the engine on the GPU thread and returns PNG bytes.
5. The use case returns a response record. The HTTP server hands it to `HtmlPresenter`, which writes the HTML fragment.

A batch is a chain of requests, one per image. Progress is a poll of `/progress`. A rewrite is one request of its own, and its phase is a poll of `/rewrite/state`: the page offers a cancel only while the model is writing, because a stop cannot land during the load.

## Add a backend

1. Write `l3_interface_adapters/gateways/<name>/capabilities.py`. Declare the modes, the params with their ranges and defaults, the reference limits, and the time estimate. Leave out Looks and templates until you test them on this model. Then pick the options that passed from the shared `gateways/prompt_aids.py` with `pick_looks`.
2. Write `<name>_backend_gateway.py` with a `<Name>BackendGateway` that implements `ImageBackendGateway`: `capabilities`, `load`, `run` and `release`. `run` reports each step and raises `Cancelled` when `should_stop()` turns true.
3. Write a builder next to `qwen21_backend` in `l4_frameworks_and_drivers/main.py` and add it to `BACKENDS`. Give it a section in `studio.toml`, and read each setting it cannot do without through `config.required`.
4. Add a gateway test at the mirrored path under `tests/`, with a `live` test that loads the real weights. Mock the engine for the unit test, so it runs with no model.
5. Run it with `uv run studio --backend <name>`.

The page knows two mode ids, `generate` and `edit`, and the params `size`, `resolution`, `steps`, `guidance`, `cfg`, `strength` and `negative`. An edit may also carry a marked region: the page appends it as the last image of the run, and replaces the prompt's `[the region you marked]` with that image's number. Only a mode that declares `region_marking` is offered the tool. A backend declares the ones it supports. A new kind of param needs a control in `web/page.html`.

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
- `tests/e2e/` holds browser checks. Each script names how to run it in its first lines. `verify_capabilities.py` needs no GPU. `verify_page.py` and `verify_backends.py` run real models against a running server. `verify_storage.py` checks the images the browser keeps, and the stub is enough for it. `verify_ui.py` checks the controls: the mode, the size chips, the Look rows, the Advanced panel, a run, a cancel, and the rewrite. It binds to roles, accessible names and the ids the page publishes, never to a decorative class, so a change to how the page is drawn does not move it.
