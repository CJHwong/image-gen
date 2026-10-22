# Model plugin contract — API version 1

Open Imagine discovers installed distributions using Python's
[entry-point specification](https://packaging.python.org/en/latest/specifications/entry-points/).
It does not scan arbitrary folders or modify its own source. Discovery reads metadata;
only explicitly visible plugins are imported. `--all-backends` makes all installed models visible.

| Workspace | Entry point group | Public types | Gateway |
|---|---|---|---|
| Image | `open_imagine.models.image` | `studio.plugins.image` | `ImageBackendGateway` |
| Video | `open_imagine.models.video` | `studio.plugins.video` | `VideoBackendGateway` |
| Voice | `open_imagine.models.audio` | `studio.plugins.audio` | `VoiceBackendGateway` |

Each entry point resolves to `studio.plugins.ModelPlugin`. This frozen record has:

| Field | Contract |
|---|---|
| `capabilities` | The corresponding media capability record; `backend_id` equals the entry point name. |
| `create(context)` | A cheap factory returning that media's gateway with exactly the declared capabilities. |
| `rewriter(context)` | Optional Image/Video `PromptRewriterGateway` factory. Omit to hide Rewrite. |
| `api_version` | `1`. Unsupported versions fail at startup with the plugin's name. |

Wrong media types, missing dependencies of a visible plugin, conflicting IDs, invalid factories,
and changed capability records produce named startup errors. Hidden plugin code is not imported.
Stub mode imports the declaration but calls neither its gateway nor rewriter factory.
A declaration must therefore import no model engine or load any weights.

## Gateway lifecycle

Implement `capabilities`, `run`, `release`, and Image/Voice `load`. Constructors, factories and
`capabilities()` must be lightweight. `load()` is idempotent. `run()` may lazily call it.
`release()` returns all owned model memory and tolerates repeated calls. A released gateway
must be able to load again. Never start a second independent GPU worker or operation queue.

Image methods execute on Studio's model thread. Video and Voice use their existing execution
paths; an adapter that requires thread affinity must confine its own engine calls. Studio
reserves the common operation lock and releases the previous model's residency before a run.

Report actual `(step, total)` through Image/Voice progress callbacks, and `(step, total, seed)`
for Video. Do not invent progress during loading or save. Observe cancellation at step boundaries
and raise `studio.plugins.<media>.Cancelled`. Owned subprocesses must terminate on cancellation;
`context.run_process` provides that behavior. Map expected engine failures to `InvalidJob` or
another public Studio error with a useful message, without publishing partial output as success.

Batch policy remains in Studio. Image/Voice can override `prepare_batch` to share preparation.
Video can override `run_batch` for engine reuse or use its ordered sequential fallback. Preserve
item order, per-item seeds, cancellation and completion callbacks. Respect the advertised batch limit.

## Inputs and outputs

| Media | Input | Output |
|---|---|---|
| Image | `ImageJob`, options, PNG reference bytes | `ImageResult` with encoded PNG bytes, dimensions, seed and steps |
| Video | `VideoJob`, geometry/timing, image/audio/clip conditioning | `VideoResult` with encoded MP4 bytes and actual output settings |
| Voice | `SpeechJob`, options, mono WAV references | `SpeechResult` with encoded WAV bytes, seconds, sample rate, seed and steps |

Use each media's existing mode and parameter contract. Plugin version 1 adds models to the
current workspaces; it does not inject arbitrary HTML, add a fourth media type, or invent new
operation schemas. Video exposes its current geometry, timing, seed and conditioning controls;
engine-specific fixed values can come from plugin configuration. Image and Voice options are
validated against the selected model's declared parameter specs. Existing form controls apply
where supported; additional custom UI widgets require host support.

The HTTP API remains unchanged. Select the installed backend ID in ordinary requests,
inspect `/api/v1/studio` first, and use `/api/v1/operations` for batches and shared status.
A missing rewriter is model-specific; a Video plugin never inherits LTX's Gemma rewriter.
Automatic native enhancement inside generation is the model gateway's responsibility.

## Process context

`PluginContext.settings` contains a copy of that model's `studio.toml` section, with paths
resolved using the same rules as built-ins. `PluginContext.run_process` takes a command list,
optional `cancelled` and stderr `consume` callbacks, and keyword arguments including
`timeout_seconds`, `environment`, and required `failure_message` (a callable accepting `(return_code, recent_lines)` and returning an error message).
It returns no value; use temporary files for binary output, as the example Video gateway does.
The host owns process termination, not engine-specific output parsing.

## Compatibility and installation

API version 1 identifies this contract independently of the plugin package's version. Install
plugins into the environment running Studio, for example with `uv run --with <package> studio`.
Restart after installing or updating. Existing built-in IDs, configuration and default model
visibility remain unchanged. Plugin-only configurations do not inherit the built-ins' MLX platform gate;
a plugin owns its engine/platform checks at runtime. This does not remove the host package's
own installation requirements.
