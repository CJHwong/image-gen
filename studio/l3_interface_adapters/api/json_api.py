"""The JSON API: the page's own use cases, with JSON in and JSON out.

The page posts a form and draws an HTML fragment from its answer. A program cannot
read that fragment, so this adapter sits beside it and speaks JSON. It does not
re-implement a rule: a JSON body is turned into the same form the page sends, and
the same controller and use cases answer, so a limit or a refusal cannot differ
between the two doors.

A batch is one request here. The page follows a chain, one image per request, and
this reads that chain to its end and answers with every image in one document.
"""

import base64
import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from studio.l1_entities.errors import InvalidJob, StudioError
from studio.l1_entities.run_progress import RunProgress
from studio.l1_entities.video_job import VideoResult
from studio.l2_use_cases.describe_studio_use_case import StudioView
from studio.l2_use_cases.rewrite_prompt_use_case import RewriteResponse
from studio.l2_use_cases.run_image_use_case import NextRun, RunImageResponse
from studio.l3_interface_adapters.api.openapi import openapi_document
from studio.l3_interface_adapters.controllers.form_controller import FormController
from studio.l3_interface_adapters.controllers.video_controller import VideoController

# A batch is a chain of runs, and a chain with no end would hold one HTTP request
# open forever. The page's own count control stops well below this.
BATCH_LIMIT = 16


class JsonApi:
    def __init__(self, controller: FormController, video: VideoController | None = None) -> None:
        self._controller = controller
        self._video = video

    def studio(self) -> dict[str, Any]:
        return studio_document(self._controller.page())

    @staticmethod
    def openapi() -> dict[str, Any]:
        return openapi_document()

    def image_run(self, payload: Mapping[str, object], mode: str) -> dict[str, Any]:
        response = self._controller.run(image_form(payload, mode))
        images = [image_document(response)]
        while response.next_run is not None:
            if len(images) >= BATCH_LIMIT:
                raise InvalidJob(f"A batch may hold at most {BATCH_LIMIT} images.")
            response = self._controller.run(next_form(response.next_run))
            images.append(image_document(response))
        return {"images": images}

    def image_rewrite(self, payload: Mapping[str, object]) -> dict[str, Any]:
        return rewrite_document(self._controller.rewrite(rewrite_form(payload, "image")))

    def video_rewrite(self, payload: Mapping[str, object]) -> dict[str, Any]:
        return rewrite_document(self._controller.rewrite(rewrite_form(payload, "video")))

    def progress(self) -> dict[str, Any]:
        return progress_document(self._controller.progress())

    def cancel_image(self) -> None:
        self._controller.cancel()

    def cancel_rewrite(self) -> None:
        self._controller.cancel_rewrite()

    def video_run(self, payload: Mapping[str, object], mode: str) -> VideoResult:
        # The route names the mode, so a body cannot ask the generate route to edit a clip.
        body = {**payload, "mode": mode}
        # A caller that does not want to stop the render should not have to name it. The
        # controller needs an id to tell two renders apart, so one is made here.
        if not body.get("request_id"):
            body["request_id"] = uuid.uuid4().hex
        return self._video_backend().run(body)

    def cancel_video(self, payload: Mapping[str, object]) -> bool:
        """Stop one render. A caller that names none stops the one in flight, which is
        the only render this single-GPU studio can be running."""
        body = dict(payload)
        if not body.get("request_id"):
            active = self._controller.progress().request_id
            if not active:
                raise InvalidJob("No video render is active.")
            body["request_id"] = active
        return self._video_backend().cancel(body)

    def _video_backend(self) -> VideoController:
        if self._video is None:
            raise StudioError("Video generation is not configured.")
        return self._video


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


def image_document(response: RunImageResponse) -> dict[str, Any]:
    image = response.image
    return {
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
        }
    return {"image": image, "video": video, "rewrite_modes": list(view.rewrite_modes)}
