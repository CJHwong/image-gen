<h1 align="center"><img src="docs/images/logo.svg" width="120" alt=""><br>Open Imagine</h1>

A local Image, Video, and Voice studio for Apple Silicon, with a shared UI and API.

- **Image:** generate and edit with Qwen Image Turbo, references, and region marking.
- **Video:** create clips with LTX-2.5 from text, keyframes, and audio; apply model-specific editing effects.
- **Voice:** generate speech and clone voices with Drama-3; use AuK for voice design and instruction edits.

Run ordered batches through the API and watch progress and results in the browser, synchronized across tabs.

![Image editing in Open Imagine, with a before-and-after comparison](docs/images/hero.jpg)

## Quick start

Requires an Apple Silicon Mac and [uv](https://docs.astral.sh/uv/). Development and model checks use 64 GB of unified memory.

```sh
git clone https://github.com/CJHwong/open-imagine.git
cd open-imagine
uv run studio
```

Open **http://127.0.0.1:8765**. Models load on first use. The default Image model downloads about 32.5 GB;
Video needs [engine setup](docs/how-to/set-up-models.md#video-ltx-25). Use `uv run studio --stub` to explore without models.

## Documentation

| I want to… | Read |
|---|---|
| Learn the workflow | [Generate and edit a first image](docs/tutorials/first-image.md) |
| Complete a task | [Set up models](docs/how-to/set-up-models.md) · [Work with media](docs/how-to/work-with-media.md) · [Use the API](docs/how-to/use-the-api.md) |
| Look up a setting or contract | [CLI and configuration](docs/reference/configuration.md) · [Models](docs/reference/models.md) · [API](API.md) |
| Understand the design | [Shared operations](docs/explanation/operations-and-storage.md) · [Measurements](docs/explanation/design-decisions.md) · [Architecture](studio/ARCHITECTURE.md) |

[All documentation](docs/README.md) · [Model licenses](docs/reference/model-licenses.md)

The rendered API reference with request examples is at **http://127.0.0.1:8765/api/docs**.
