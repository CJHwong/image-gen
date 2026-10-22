"""The JSON API: the page's own use cases, with JSON in and JSON out.

The page posts a form and draws an HTML fragment from its answer. A program cannot
read that fragment, so this adapter sits beside it and speaks JSON. It does not
re-implement a rule: a JSON body is turned into the same form the page sends, and
the same controller and use cases answer, so a limit or a refusal cannot differ
between the two doors.

A batch is one request here. The page follows a chain, one image per request, and
this reads that chain to its end and answers with every image in one document.
"""

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from typing import Any

from studio.l1_entities.errors import Cancelled, InvalidJob, OperationMissing, StudioError, UnknownBackend
from studio.l1_entities.operation import OperationOutput
from studio.l1_entities.video_job import VideoResult
from studio.l1_entities.voice_job import SpeechResult
from studio.l2_use_cases.boundaries.operation_gateway import OperationGateway
from studio.l2_use_cases.complete_operation_use_case import CompleteOperationUseCase
from studio.l2_use_cases.prepare_batch_use_case import BATCH_LIMIT, PrepareBatchUseCase
from studio.l2_use_cases.run_image_use_case import RunImageResponse
from studio.l3_interface_adapters.api.audio_trim import trim_audio
from studio.l3_interface_adapters.api.openapi import openapi_document
from studio.l3_interface_adapters.api.prompt_builder import prepare_prompt
from studio.l3_interface_adapters.api.request_mapper import image_form, next_form, rewrite_form
from studio.l3_interface_adapters.controllers.form_controller import FormController
from studio.l3_interface_adapters.controllers.video_controller import VideoController
from studio.l3_interface_adapters.controllers.voice_controller import VoiceController
from studio.l3_interface_adapters.presenters.json_presenter import (
    image_document,
    native_image_progress,
    operation_document,
    progress_document,
    rewrite_document,
    studio_document,
)


class JsonApi:
    def __init__(
        self,
        controller: FormController,
        video: VideoController | None = None,
        voice: VoiceController | None = None,
        *,
        operations: OperationGateway,
        completion: CompleteOperationUseCase,
        batches: PrepareBatchUseCase,
    ) -> None:
        self._controller = controller
        self._video = video
        self._voice = voice
        self._operations = operations
        self._completion = completion
        self._batches = batches

    def trim_audio(self, payload: Mapping[str, Any]) -> tuple[bytes, float]:
        return trim_audio(payload)

    def image_form_run(self, form: Mapping[str, str]) -> tuple[RunImageResponse, dict[str, Any]]:
        operation_id = form.get("operation_id", "")
        if operation_id:
            index = form.get("index", "")
            if not index.isdigit():
                raise InvalidJob("index must be a whole number")
            operation = self._operations.resume(operation_id, int(index), form.get("client_id", ""))
        else:
            operation = self.reserve({**form, "kind": "image"}, source="ui")
            operation_id = operation["id"]
        try:
            response = self._controller.run(form)
            image = image_document(response)
            result = self._operations.append_image(operation_id, image)
            if response.next_run is None:
                self._operations.finish(operation_id, result)
            else:
                next_run = replace(
                    response.next_run, options={**response.next_run.options, "operation_id": operation_id}
                )
                response = replace(response, next_run=next_run)
                self._operations.pause(operation_id, next_run.index)
            return response, {**operation, "result_completed_at": image["completed_at"]}
        except Exception as error:
            self._operations.fail(operation_id, error)
            raise

    def image_run(self, payload: Mapping[str, object], mode: str) -> dict[str, Any]:
        return self.observe("image", {**payload, "mode": mode}, lambda: self._image_run(payload, mode))

    def video_run(self, payload: Mapping[str, object], mode: str) -> VideoResult:
        return self.observe("video", {**payload, "mode": mode}, lambda: self._video_run(payload, mode))

    def observe(
        self,
        kind: str,
        payload: Mapping[str, object],
        action: Callable,
        serialize: Callable | None = None,
        *,
        source: str = "api",
    ):
        operation = self.reserve({**payload, "kind": kind}, source=source)
        return self.complete(operation["id"], action, serialize)

    def reserve(self, payload: Mapping[str, object], *, source: str = "api") -> dict[str, Any]:
        kind = payload.get("kind")
        if kind not in ("image", "video", "rewrite", "voice"):
            raise InvalidJob("kind must be image, video, voice or rewrite")
        workspace = payload.get("workspace") or (kind if kind in ("video", "voice") else "image")
        if workspace not in ("image", "video", "voice"):
            raise InvalidJob("workspace must be image, video or voice")
        if kind != "rewrite" and workspace != kind:
            raise InvalidJob("workspace must match the operation kind")
        mode = payload.get("mode") or (
            self._voice_backend().model_capabilities(payload.get("backend", "")).default_mode
            if kind == "voice"
            else "generate"
        )
        if mode not in (("generate", "clone", "design", "edit") if kind == "voice" else ("generate", "edit")):
            raise InvalidJob("mode must be generate or edit")
        if (
            kind == "voice"
            and "backend" in payload
            and (not isinstance(payload["backend"], str) or not payload["backend"])
        ):
            raise InvalidJob("backend must be a nonempty Voice model id")
        document = self.studio().get(workspace)
        backend = payload.get("backend") or (document["active"] if document else "")
        model = next((one["name"] for one in document["backends"] if one["id"] == backend), "") if document else ""
        batch_metadata = {}
        if "items" in payload:
            batch_metadata["batch_total"] = len(self._batches.execute({**payload, "backend": backend}))
        excluded = {"references", "reference", "clip", "audio", "reference_token", "items"}
        settings = {key: value for key, value in payload.items() if key not in excluded}
        return operation_document(
            self._operations.begin(
                {
                    **batch_metadata,
                    "kind": kind,
                    "source": source,
                    "workspace": workspace,
                    "mode": mode,
                    "backend": backend,
                    "model": model,
                    "prompt": payload.get("prompt", payload.get("text", "")),
                    "width": payload.get("width"),
                    "height": payload.get("height"),
                    "num_frames": payload.get("num_frames"),
                    "frame_rate": payload.get("frame_rate"),
                    "settings": settings,
                    "client_id": payload.get("client_id", ""),
                    "library_id": payload.get("library_id", ""),
                }
            )
        )

    def complete(
        self, operation_id: str, action: Callable, serialize: Callable | None = None, observed: dict | None = None
    ):
        def adapted_action():
            result = action()
            return OperationOutput(result, serialize(result) if serialize else result)

        completed = self._completion.execute(operation_id, adapted_action)
        if observed is not None:
            observed["finished_at"] = completed.finished_at
        return completed.value

    def execute_operation(self, operation: dict[str, Any], payload: Mapping[str, object]):
        mode = operation["mode"]
        kind = operation["kind"]
        body = {key: value for key, value in payload.items() if key not in ("kind", "workspace")}

        def action():
            if self._operations.get(operation["id"])["status"] == "stopping":
                raise Cancelled("The operation was cancelled before it started.")
            if "items" in body:
                return self._batch(operation, body)
            if kind == "voice":
                voice = self._voice_backend()
                selected = body.get("backend", voice.active_id())
                voice.switch({"backend": selected})
                return voice.run({**body, "backend": selected})
            if kind == "image":
                return self._image_run(body, mode)
            if kind == "video":
                return self._video_run(body, mode)
            return rewrite_document(self._controller.rewrite(rewrite_form(body, operation["workspace"])))

        return self.complete(operation["id"], action, observed=operation)

    def operation(self, operation_id: str) -> dict[str, Any]:
        return self._operation_document(self._operations.get(operation_id))

    def _operation_document(self, operation: dict[str, Any]) -> dict[str, Any]:
        operation = operation_document(operation)
        if operation["status"] in ("running", "stopping"):
            operation["progress"] = self.rewrite_state() if operation["kind"] == "rewrite" else self.progress()
        else:
            operation["progress"] = {"running": False, "stage": operation["status"], "step": 0, "total": 0}
        if operation.get("batch_total"):
            progress = operation["progress"]
            total = progress.get("total") or 1
            index = operation.get("batch_index", 1)
            completed = operation.get("batch_completed", 0)
            step = max(completed * total, (index - 1) * total + (progress.get("step") or 0))
            operation["progress"] = {**progress, "step": step, "total": operation["batch_total"] * total}
        elif operation["source"] == "ui" and operation["kind"] == "image":
            operation["progress"] = native_image_progress(operation["progress"])
        return operation

    def operation_result(self, operation_id: str):
        return self._operations.result(operation_id)

    def state(self) -> dict[str, Any]:
        operations = [self._operation_document(one) for one in self._operations.recent()]
        active = next((one for one in operations if one["status"] in ("running", "stopping")), None)
        return {"active": active, "operations": operations, "studio": self.studio()}

    def cancel_operation(self, operation_id: str) -> None:
        operation = self._operations.stopping(operation_id)
        if operation["kind"] == "image" and operation["status"] == "stopping":
            self._controller.watch_cancel(
                operation_id,
                lambda: self._operations.cancelling(operation_id),
                lambda release: self._operations.escalate(operation_id, release),
            )

    def cancellation_requested(self) -> bool:
        active = self._operations.active()
        return active is not None and active["status"] == "stopping"

    def switch_backend(self, payload: Mapping[str, object], workspace: str) -> None:
        backend = payload.get("backend")
        if not isinstance(backend, str):
            raise InvalidJob("backend must be a model id")
        controller = self._workspace_controller(workspace)
        self._operations.exclusive(lambda: controller.switch({"backend": backend}))

    def release_model(self) -> None:
        self._operations.exclusive(self._controller.release_model)

    def rewrite_state(self) -> dict[str, Any]:
        return asdict(self._controller.rewrite_state())

    def studio(self) -> dict[str, Any]:
        document = studio_document(self._controller.page())
        if self._voice is not None:
            document["voice"] = {
                "active": self._voice.active_id(),
                "backends": self._voice.backends(),
                "capabilities": self.voice_capabilities(),
            }
        return document

    def backend_capabilities(self, workspace, backend_id):
        controller = self._workspace_controller(workspace)
        try:
            capabilities = (
                controller.model_capabilities(backend_id)
                if workspace == "voice"
                else controller.capabilities(backend_id)
            )
            return asdict(capabilities)
        except UnknownBackend as error:
            raise OperationMissing(str(error)) from None

    def _workspace_controller(self, workspace):
        if workspace == "voice":
            return self._voice_backend()
        return self._controller if workspace == "image" else self._video_backend()

    def voice_capabilities(self):
        return self._voice_backend().capabilities()

    def _voice_backend(self):
        if self._voice is None:
            raise StudioError("Voice generation is not configured.")
        return self._voice

    def item_result(self, operation_id, index):
        if isinstance(index, str):
            if not index.isdecimal():
                raise InvalidJob("The batch item index must be a positive integer.")
            index = int(index)
        return self._operations.item_result(operation_id, index)

    def _batch(self, operation, body):
        items = self._batches.execute({**body, "kind": operation["kind"], "backend": operation["backend"]})
        effective_items = items
        operation_id = operation["id"]
        manifest = {"items": [], "completed": 0, "batch_total": len(items)}
        self._operations.retain(operation_id, manifest)

        def started(index, total):
            self._operations.batch_started(operation_id, index, total)

        def completed(index, result):
            nonlocal manifest
            item = items[index - 1]
            metadata = {
                "index": index,
                "kind": operation["kind"],
                "status": "succeeded",
                "result_url": f"/api/v1/operations/{operation_id}/items/{index}/result",
                "prompt": effective_items[index - 1].get("prompt", item.get("text", "")),
                "settings": {
                    key: value for key, value in item.items() if key not in ("references", "reference", "audio", "clip")
                },
                "completed_at": time.time(),
            }
            if isinstance(result, VideoResult):
                metadata.update(
                    width=result.width,
                    height=result.height,
                    num_frames=result.num_frames,
                    frame_rate=result.frame_rate,
                    seed=result.seed,
                    stub=result.stub,
                )
            if isinstance(result, SpeechResult):
                metadata.update(
                    seconds=result.seconds,
                    sample_rate=result.sample_rate,
                    seed=result.seed,
                    prompt=result.text or metadata["prompt"],
                )
            manifest = self._operations.batch_completed(operation_id, result, metadata)

        if operation["kind"] == "video":
            self._select_requested_backend("video", body)
            effective_items = [
                self._prompt_payload(item, str(item.get("mode") or "generate"), video=True) for item in items
            ]
            self._video_backend().run_batch(
                [{**item, "request_id": operation_id} for item in effective_items],
                completed,
                started,
                self.cancellation_requested,
            )
        elif operation["kind"] == "voice":
            voice = self._voice_backend()
            voice.switch({"backend": operation["backend"]})
            voice.run_batch(items, completed, started, self.cancellation_requested)
        else:
            self._select_requested_backend("image", {"backend": operation["backend"]})
            effective_items = [self._prompt_payload(item, str(item.get("mode") or "generate")) for item in items]
            forms = [image_form(item, str(item.get("mode") or "generate")) for item in effective_items]
            self._controller.run_batch(
                forms,
                lambda index, response: completed(index, {"images": [image_document(response)]}),
                started,
                self.cancellation_requested,
            )
        return manifest

    @staticmethod
    def openapi() -> dict[str, Any]:
        return openapi_document()

    def _prompt_payload(self, payload: Mapping[str, object], mode: str, *, video: bool = False) -> dict[str, Any]:
        if not any(key in payload for key in ("looks", "template", "per_reference_prompts")):
            return dict(payload)
        backend_id = str(payload.get("backend") or "")
        if video:
            capabilities = self._video_backend().capabilities(backend_id)
            specification = asdict(capabilities.mode(mode))
            specification["templates"] = asdict(capabilities)["templates"] if mode == "generate" else []
        else:
            backend_id = backend_id or self._controller.page().active.backend_id
            specification = asdict(self._controller.capabilities(backend_id).mode(mode))
        return prepare_prompt(payload, specification, video=video)

    def _image_run(self, payload: Mapping[str, object], mode: str) -> dict[str, Any]:
        self._select_requested_backend("image", payload)
        body = self._prompt_payload(payload, mode)
        rows = body.pop("per_reference_prompts", [])
        response = self._controller.run(image_form(body, mode))
        images = [image_document(response)]
        operation = self._operations.active()
        assert operation is not None
        self._operations.retain(operation["id"], {"images": images.copy()})
        while response.next_run is not None:
            if len(images) >= BATCH_LIMIT:
                raise InvalidJob(f"A batch may hold at most {BATCH_LIMIT} images.")
            form = next_form(response.next_run)
            if rows:
                form["prompt"] = rows[(response.next_run.index - 1) % len(rows)]
            response = self._controller.run(form)
            images.append(image_document(response))
            self._operations.retain(operation["id"], {"images": images.copy()})
        return {"images": images}

    def image_rewrite(self, payload: Mapping[str, object]) -> dict[str, Any]:
        return self.observe(
            "rewrite",
            {**payload, "workspace": "image"},
            lambda: rewrite_document(self._controller.rewrite(rewrite_form(payload, "image"))),
        )

    def video_rewrite(self, payload: Mapping[str, object]) -> dict[str, Any]:
        return self.observe(
            "rewrite",
            {**payload, "workspace": "video"},
            lambda: rewrite_document(self._controller.rewrite(rewrite_form(payload, "video"))),
        )

    def progress(self) -> dict[str, Any]:
        return progress_document(self._controller.progress())

    def cancel_image(self) -> None:
        active = self._operations.active()
        if active is not None and active["kind"] == "image":
            self.cancel_operation(active["id"])
        else:
            self._controller.cancel()

    def cancel_rewrite(self) -> None:
        active = self._operations.active()
        if active is not None and active["kind"] == "rewrite":
            self.cancel_operation(active["id"])
        else:
            self._controller.cancel_rewrite()

    def _select_requested_backend(self, workspace, payload):
        backend = payload.get("backend")
        if not backend:
            return
        if not isinstance(backend, str):
            raise InvalidJob("backend must be a model id")
        document = self.studio().get(workspace)
        if document and backend != document["active"]:
            controller = self._workspace_controller(workspace)
            controller.switch({"backend": backend})

    def _video_run(self, payload: Mapping[str, object], mode: str) -> VideoResult:
        # The route names the mode, so a body cannot ask the generate route to edit a clip.
        self._select_requested_backend("video", payload)
        body = {**self._prompt_payload(payload, mode, video=True), "mode": mode}
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
