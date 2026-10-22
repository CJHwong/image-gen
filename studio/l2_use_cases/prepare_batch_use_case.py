"""One ordered batch shares defaults, a reservation, and retained item results."""

from collections.abc import Mapping
from typing import Any

from studio.l1_entities.errors import InvalidJob

BATCH_LIMIT = 16


class PrepareBatchUseCase:
    def execute(self, payload: Mapping[str, object]) -> list[dict[str, Any]]:
        """Validate the envelope before any item can consume model memory."""
        kind = payload.get("kind")
        if not isinstance(kind, str) or kind not in ("image", "video", "voice"):
            raise InvalidJob("A batch kind must be image, video or voice.")
        items = payload.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= BATCH_LIMIT:
            raise InvalidJob(f"items must contain between 1 and {BATCH_LIMIT} objects.")
        defaults = {key: value for key, value in payload.items() if key != "items"}
        normalized = []
        for item in items:
            if not isinstance(item, Mapping):
                raise InvalidJob("Each entry in items must be an object.")
            body = {**defaults, **item}
            _check_item(body, defaults, kind)
            normalized.append(body)
        return normalized


def _check_item(body: Mapping[str, Any], defaults: Mapping[str, Any], kind: str) -> None:
    if kind == "video" and body.get("fast_mode", False) != defaults.get("fast_mode", False):
        raise InvalidJob("Each video batch item must use the same fast_mode.")
    for key, expected in (("kind", kind), ("workspace", kind), ("backend", defaults.get("backend"))):
        if key in body and body[key] != expected:
            raise InvalidJob(f"Each batch item must use the same {key}.")
    for key in ("items", "total", "index", "reference_token"):
        if key in body:
            raise InvalidJob(f"A batch item cannot contain {key}.")
    if type(body.get("count", 1)) is not int or body.get("count", 1) != 1:
        raise InvalidJob("A batch item produces one result; count must be 1.")
    if body.get("each_reference"):
        raise InvalidJob("A batch item produces one result; each_reference must be false.")
