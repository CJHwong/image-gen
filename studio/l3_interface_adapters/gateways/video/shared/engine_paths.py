"""Resolve the engine executable named by adapter configuration."""

import shutil
from pathlib import Path

from studio.l1_entities.errors import StudioError


def checked_executable(value: str, message: str) -> str:
    if not value:
        raise StudioError(message)
    path = Path(value).expanduser()
    if path.is_file():
        return str(path.absolute())
    found = shutil.which(value)
    if found:
        return found
    raise StudioError(message)
