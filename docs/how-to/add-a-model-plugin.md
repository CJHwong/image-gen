# Add a model without editing Open Imagine

Install a Python package that exports an Open Imagine model entry point. Enable its ID
in your configuration or use `--all-backends`. Restart Studio after installing or updating it.
The model appears in its workspace's selector, `/api/v1/studio`, and the existing operation API.

## Try the runnable example

From the Open Imagine checkout:

```sh
uv run --with ./examples/model_plugin studio --config examples/model_plugin/studio.toml
```

This is a real external package, discovered from its installed metadata. It supplies
**Example Image** (a solid-color PNG), **Example Video** (an FFmpeg test clip), and
**Example Voice** (a WAV tone). These are CPU contract demonstrations, not trained models.
Video requires `ffmpeg` on PATH. Add `--stub` to exercise their forms without calling their factories.

To offer the example alongside the built-in models:

```sh
uv run --with ./examples/model_plugin studio --all-backends
```

No model is loaded by starting the server or selecting a model. Factories and capability
records must stay cheap; put engine imports, downloads and weight loading inside `load`/`run`.

## Create your package

Copy [the example package](../../examples/model_plugin/pyproject.toml). Keep one gateway
per model, under modules that identify Image, Video or Audio. Replace the example's engine
work and capabilities with your model's actual implementation and supported settings.
Do not import a built-in model gateway to advertise a different model.

Register the module-level `plugin` record in your package's `pyproject.toml`:

```toml
[project.entry-points."open_imagine.models.image"]
acme_image = "acme_models.image:plugin"

[project.entry-points."open_imagine.models.video"]
acme_video = "acme_models.video:plugin"

[project.entry-points."open_imagine.models.audio"]
acme_voice = "acme_models.audio:plugin"
```

A package can supply one model or several; omit unused groups. IDs use lowercase letters,
digits and underscores, beginning with a letter. They must be unique across all three
workspaces and cannot replace built-ins. Set `capabilities.backend_id` to the entry point ID.
Names, badges, modes, sizes, parameters, templates, references and estimates come from capabilities.

Export a record, not an already loaded engine:

```python
from studio.plugins import ModelPlugin
from studio.plugins.image import ImageBackendGateway

# CAPABILITIES is a studio.plugins.image.Capabilities record.
# AcmeImageGateway implements ImageBackendGateway.
plugin = ModelPlugin(
    capabilities=CAPABILITIES,
    create=lambda context: AcmeImageGateway(context.settings),
    api_version=1,
)
```

Install and enable it without changing Open Imagine's source:

```sh
uv run --with /path/to/acme-models studio --config /path/to/my-studio.toml
```

Published packages work in the same way with `--with acme-models`. Declare engine dependencies
in your plugin package; pin an isolated child environment when its dependencies conflict with
other engines. Installed plugins are executable Python packages; install packages you trust.

## Configure and test it

Use the existing workspace settings and a section named after the model ID:

```toml
# Other workspace settings can keep their existing built-ins.
default_backend = "acme_image"
visible_backends = ["acme_image"]

[acme_image]
model_dir = "~/Models/acme-image"
quantize = 8
```

The factory receives resolved paths through `context.settings`, a read-only mapping.
A backend's engine-specific fixed settings also belong in this section. `context.run_process`
is the host's cancellable subprocess driver, used by the Video example to run FFmpeg.

Use `--stub` first, then test real output through `/api/v1/operations` and the UI. Check Generate,
Edit or Clone where declared, cancellation, model switching, and ordered batches. Read capability
limits from discovery; do not assume the defaults of a built-in model apply to a plugin.
The shared operation lock, progress, cancellation and result storage are still owned by Studio.

See [the plugin contract](../reference/model-plugins.md) for lifecycle and media types, and
[the backend validation method](../../AGENTS.md#backend-flow) before publishing real capabilities.
