"""Plain JSON view models shared by HTTP entry points."""

import base64
import re
import time
from dataclasses import asdict
from typing import Any

from studio.l1_entities.run_progress import RunProgress
from studio.l2_use_cases.describe_studio_use_case import StudioView
from studio.l2_use_cases.rewrite_prompt_use_case import RewriteResponse
from studio.l2_use_cases.run_image_use_case import RunImageResponse


def image_document(response: RunImageResponse) -> dict[str, Any]:
    image = response.image
    return {
        "completed_at": time.time(),
        "png_base64": base64.b64encode(image.png).decode("ascii"),
        "width": image.width,
        "height": image.height,
        "seed": image.seed,
        "steps": image.steps,
        "elapsed": round(response.elapsed, 1),
        "position": response.position,
        "mode": response.mode,
        "prompt": response.prompt,
        "reference": response.reference,
    }


def rewrite_document(response: RewriteResponse) -> dict[str, Any]:
    if response.cancelled:
        return {"cancelled": True}
    return {"prompt": response.prompt, "size": response.size, "elapsed": round(response.elapsed, 1)}


def native_image_progress(progress: dict[str, Any]) -> dict[str, Any]:
    # The label and counters share one snapshot, so a continuation cannot combine
    # the next image's index with the previous image's finished counters.
    match = re.fullmatch(r"([1-9]\d*) of ([1-9]\d*)", progress.get("label", ""))
    if match is None:
        return progress
    index, count = map(int, match.groups())
    if count < 2 or index > count:
        return progress
    total = progress["total"] or 1
    step = progress["step"] if progress["total"] else 0
    return {**progress, "step": (index - 1) * total + step, "total": count * total}


def progress_document(state: RunProgress) -> dict[str, Any]:
    return {
        "running": state.running,
        "stage": state.stage,
        "step": state.step,
        "total": state.total,
        "phase": state.phase,
        "label": state.label,
        "kind": state.kind,
        "stopping": state.stopping,
        "request_id": state.request_id,
    }


def studio_document(view: StudioView) -> dict[str, Any]:
    """What the page draws, in the page's own terms, so a caller can read the sizes,
    modes, Looks and templates a model offers before it sends one."""
    image = {
        "active": view.active.backend_id,
        "backends": [{"id": one, "name": name, "description": text} for one, name, text in view.backends],
        "capabilities": asdict(view.active),
    }
    video = None
    if view.active_video is not None:
        video = {
            "active": view.active_video.backend_id,
            "backends": [{"id": one, "name": name, "description": text} for one, name, text in view.video_backends],
            "capabilities": asdict(view.active_video),
            "rewrite_modes": list(view.video_rewrite_modes),
        }
    return {"image": image, "video": video, "rewrite_modes": list(view.rewrite_modes)}


def operation_document(record: dict[str, Any]) -> dict[str, Any]:
    """Routes belong to the HTTP view, not the shared operation store."""
    document = dict(record)
    retained = document.pop("result_retained")
    operation_id = document["id"]
    document["status_url"] = f"/api/v1/operations/{operation_id}"
    document["result_url"] = f"/api/v1/operations/{operation_id}/result" if retained else None
    return document
