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
    sections: dict

    def backend(self, backend_id: str) -> dict:
        """One backend's settings. Paths are absolute, and a quantize of 0 means none."""
        return dict(self.sections.get(backend_id, {}))

    def required(self, backend_id: str, key: str):
        settings = self.backend(backend_id)
        if key not in settings:
            raise ConfigError(f"studio.toml has no {key} under [{backend_id}]")
        return settings[key]


def load_config(path: Path, backend: str | None = None, quantize: int | None = None) -> Config:
    """`backend` opens the page on that backend and makes sure the page offers it.
    `quantize` applies to the backend the page opens with."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    default = backend or raw["default_backend"]
    visible = tuple(raw.get("visible_backends", [default]))
    if default not in visible:
        visible = (default, *visible)
    sections = {name: _settings(value, path.parent) for name, value in raw.items() if isinstance(value, dict)}
    if quantize is not None:
        sections.setdefault(default, {})["quantize"] = quantize or None
    return Config(default_backend=default, visible_backends=visible, sections=sections)


def _settings(section: dict, base: Path) -> dict:
    settings = {}
    for key, value in section.items():
        if key.endswith(("_script", "_dir")):
            value = str((base / Path(value).expanduser()).resolve())
        if key == "quantize":
            value = value or None
        settings[key] = value
    return settings
