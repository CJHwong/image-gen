"""studio.toml, read once at start, with the command-line flags on top."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """studio.toml lacks something the server needs. The message names it."""


@dataclass(frozen=True)
class Config:
    default_backend: str
    visible_backends: tuple[str, ...]
    default_video_backend: str
    visible_video_backends: tuple[str, ...]
    sections: dict
    default_voice_backend: str = "drama3"
    visible_voice_backends: tuple[str, ...] = ("drama3", "auk_base", "auk")

    def backend(self, backend_id: str) -> dict:
        """One backend's settings. Paths are absolute, and a quantize of 0 means none."""
        return dict(self.sections.get(backend_id, {}))

    def required(self, backend_id: str, key: str):
        settings = self.backend(backend_id)
        if key not in settings:
            raise ConfigError(f"studio.toml has no {key} under [{backend_id}]")
        return settings[key]


def load_config(
    path: Path,
    backend: str | None = None,
    quantize: int | None = None,
    visible: tuple[str, ...] | None = None,
    visible_video: tuple[str, ...] | None = None,
    visible_voice: tuple[str, ...] | None = None,
) -> Config:
    """`backend` opens the page on that backend and makes sure the page offers it.
    `quantize` applies to the backend the page opens with. `visible` offers exactly the
    backends it names. The video and voice overrides follow the same rule."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    default = backend or raw["default_backend"]
    visible = visible if visible else tuple(raw.get("visible_backends", [default]))
    if default not in visible:
        visible = (default, *visible)
    default_video = raw.get("default_video_backend", "ltx25_mlx")
    visible_video = visible_video if visible_video else tuple(raw.get("visible_video_backends", [default_video]))
    if default_video not in visible_video:
        visible_video = (default_video, *visible_video)
    default_voice = raw.get("default_voice_backend", "drama3")
    visible_voice = visible_voice if visible_voice else tuple(raw.get("visible_voice_backends", [default_voice]))
    if default_voice not in visible_voice:
        visible_voice = (default_voice, *visible_voice)
    sections = {name: _settings(value, path.parent) for name, value in raw.items() if isinstance(value, dict)}
    if quantize is not None:
        sections.setdefault(default, {})["quantize"] = quantize or None
    return Config(
        default_backend=default,
        visible_backends=visible,
        default_video_backend=default_video,
        visible_video_backends=visible_video,
        sections=sections,
        default_voice_backend=default_voice,
        visible_voice_backends=visible_voice,
    )


def _settings(section: dict, base: Path) -> dict:
    settings = {}
    for key, value in section.items():
        if key in ("python_path", "cli_path"):
            # A venv's executable link selects the site-packages the runtime needs.
            value = str((base / Path(value).expanduser()).absolute())
        elif key.endswith(("_script", "_dir", "_path")):
            value = str((base / Path(value).expanduser()).resolve())
        if key == "quantize":
            value = value or None
        settings[key] = value
    return settings
