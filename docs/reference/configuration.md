# CLI and configuration

Run from the checkout with `uv run studio`. The console command remains `studio`.

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address. |
| `--port` | `8765` | Server port. Browser storage belongs to the address and port. |
| `--backend` | `default_backend` | Initial Image model; adds it to the offered models. |
| `--all-backends` | Off | Enable model selectors across Image, Video, and Voice. |
| `-q`, `--quantize` | Model configuration | Opening Image model quantization: 0, 3, 4, 5, 6, or 8 bits; 0 means full precision. |
| `--config` | `studio.toml` | Configuration file. |
| `--allow-origin` | None | Let a page at this origin post, such as a Tailscale serve URL. Repeat it for each origin. |
| `--stub` | Off | Simulated engines: placeholder images, a Voice test tone, and Video metadata. No model loading. |

## Settings

[studio.toml](../../studio.toml) contains the current defaults and path examples.

| Key | Meaning |
|---|---|
| `default_backend`, `visible_backends` | Initial and available Image models. |
| `default_video_backend`, `visible_video_backends` | Initial and available Video models. |
| `default_voice_backend`, `visible_voice_backends` | Initial and available Voice models. |
| Image backend `quantize` | Weight quantization; 0 is the default. |
| Image backend `model_dir` / `lora_path` | Local weights or adapter path, where supported. |
| `[mlx_video].cli_path`, `ffmpeg_path` | Separate Video executable and media tool. |
| `[mlx_video].model_ltx25`, `model_ltx23` | Video pack identifiers. |
| `[mlx_video].lora_dir`, `fetch_loras` | Effect adapter directory and opt-in download policy. |
| `[mlx_video].batch_policy` | `auto`, `enhance_only`, or `sequential`. |
| `[auk].child_script` | AuK child implementation. |
| `[drama3].child_script`, `python_path` | Drama-3 child and optional prebuilt environment. |

A workspace shows its model selector only when more than one model is offered.
Selecting a model does not load it. Paths relative to the configuration file resolve from that file.

## Development checks

```sh
uv run pytest
uv run prek run --all-files
```

The CPU suite enforces 100% statement and branch coverage for `studio/`.
Tests marked `live` require installed weights and a free GPU.
Use a fresh `uv run studio --stub --all-backends --port 8895` server for browser checks under `tests/e2e/`.
The page is read at startup; restart the stub after page changes and between suites.
