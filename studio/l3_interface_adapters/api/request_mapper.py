"""Translate JSON payloads into the legacy form transport without running a job."""

import json
from collections.abc import Mapping

from studio.l1_entities.errors import InvalidJob
from studio.l2_use_cases.run_image_use_case import NextRun


def image_form(payload: Mapping[str, object], mode: str) -> dict[str, str]:
    """A JSON body as the form the page would post, so one parser checks both doors."""
    form: dict[str, str] = {"mode": mode}
    for key, value in payload.items():
        if key == "mode" or value is None:
            continue
        form[key] = form_value(key, value)
    return form


def rewrite_form(payload: Mapping[str, object], workspace: str) -> dict[str, str]:
    form = image_form(payload, str(payload.get("mode") or "generate"))
    form["workspace"] = workspace
    return form


def form_value(key: str, value: object) -> str:
    if key == "references":
        if not isinstance(value, list):
            raise InvalidJob("references must be an array of base64 strings")
        return json.dumps([reference_text(item) for item in value])
    if isinstance(value, bool):
        return "1" if value else ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    raise InvalidJob(f"{key} must be a string, a number or a boolean")


def reference_text(item: object) -> str:
    """One reference as bare base64. A data URL is accepted, because that is what a
    browser's FileReader hands back and what a caller already has in hand."""
    text = item
    if isinstance(item, Mapping):
        text = item.get("png_base64") or item.get("data")
    if not isinstance(text, str) or not text.strip():
        raise InvalidJob("Each reference must be a base64 string or an object with png_base64")
    marker = "base64,"
    if text.startswith("data:") and marker in text:
        return text.split(marker, 1)[1].strip()
    return text.strip()


def next_form(next_run: NextRun) -> dict[str, str]:
    """The form the page builds for the next image of a batch, field for field."""
    form = {
        **next_run.options,
        "mode": next_run.mode,
        "prompt": next_run.prompt,
        "seed": str(next_run.seed),
        "total": str(next_run.total),
        "index": str(next_run.index),
        "reference_token": next_run.reference_token,
        "backend": next_run.backend,
    }
    if next_run.each_reference:
        form["each_reference"] = "1"
    if next_run.mask:
        form["mask"] = "1"
    return form
