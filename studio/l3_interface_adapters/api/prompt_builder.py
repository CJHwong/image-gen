"""Compose the prompt aids declared by the selected model."""

import re
from collections.abc import Mapping
from typing import Any

from studio.l1_entities.errors import InvalidJob

ENDINGS = ".!?\u3002\uff01\uff1f"


def prepare_prompt(payload: Mapping[str, Any], mode: Mapping[str, Any], *, video: bool = False) -> dict[str, Any]:
    body = dict(payload)
    prompt = _template(body, mode)
    positive, avoids = _looks(body.pop("looks", {}), mode)
    rows = body.get("per_reference_prompts")
    if rows is not None:
        references = body.get("references", [])
        if not mode.get("each_reference") or not body.get("each_reference") or body.get("mask"):
            raise InvalidJob("per_reference_prompts requires each_reference in a mode that supports it")
        if not isinstance(rows, list) or not rows or not isinstance(references, list) or len(rows) != len(references):
            raise InvalidJob("per_reference_prompts needs one instruction per reference")
        if not all(isinstance(row, str) for row in rows):
            raise InvalidJob("Each reference instruction must be a string")
        body["per_reference_prompts"] = [_append(_append(prompt, row), positive) for row in rows]
        prompt = body["per_reference_prompts"][0]
    else:
        prompt = _append(prompt, positive, video=video)
    if "prompt" in body or prompt:
        body["prompt"] = prompt
    if not video and avoids and any(param["id"] == "negative" for param in mode.get("params", [])):
        body["negative"] = ", ".join(filter(None, [str(body.get("negative") or "").strip(), avoids]))
        for param in mode.get("params", []):
            if param.get("with_negative"):
                body[param["id"]] = _negative_scale(body.get(param["id"]), param)
    return body


def _append(lead: str, tail: str, *, video: bool = False) -> str:
    lead, tail = lead.strip(), tail.strip()
    if not lead:
        return tail
    if not tail:
        return lead
    stop = "" if video or lead[-1] in ENDINGS else "."
    return lead + stop + " " + tail


def _template(body: dict[str, Any], mode: Mapping[str, Any]) -> str:
    name = body.pop("template", None)
    values = body.pop("template_values", {})
    if name is None:
        prompt = body.get("prompt", "")
        if not isinstance(prompt, str):
            raise InvalidJob("prompt must be a string")
        return prompt
    template = next((item for item in mode.get("templates", []) if item["name"] == name), None)
    if template is None:
        raise InvalidJob("Choose a template offered by this model and mode")
    if not isinstance(values, Mapping):
        raise InvalidJob("template_values must map each bracket name to text")

    def substitute(match: re.Match) -> str:
        value = values.get(match.group(1))
        if not isinstance(value, str) or not value.strip():
            raise InvalidJob("Fill template field: " + match.group(1))
        return value.strip()

    return re.sub(r"\[([^\]\n]+)\]", substitute, template["text"])


def _looks(selections: object, mode: Mapping[str, Any]) -> tuple[str, str]:
    if not isinstance(selections, Mapping):
        raise InvalidJob("looks must map each row name to one option")
    available = {row["name"]: row for row in mode.get("looks", [])}
    if set(selections) - set(available):
        raise InvalidJob("Choose Look rows offered by this model and mode")
    positive, avoids = [], []
    for name, row in available.items():
        selected = selections.get(name, [])
        if isinstance(selected, str):
            selected = [selected]
        if not isinstance(selected, list) or len(selected) > 1:
            raise InvalidJob("Each Look row takes at most one option")
        if not selected:
            continue
        choices = dict(row["options"])
        label = selected[0]
        if not isinstance(label, str) or label not in choices:
            raise InvalidJob("Choose a Look option offered by this model and mode")
        positive.append(choices[label])
        avoids.append(dict(row.get("avoids", [])).get(label, ""))
    return " ".join(filter(None, positive)), ", ".join(filter(None, avoids))


def _negative_scale(value: object, param: Mapping[str, Any]) -> float:
    if not isinstance(value, (int, float, str, type(None))):
        raise InvalidJob(param["id"] + " must be a number")
    try:
        number = float(value or param["default"])
    except (TypeError, ValueError):
        raise InvalidJob(param["id"] + " must be a number") from None
    return max(number, param["with_negative"])
