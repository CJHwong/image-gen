"""The HTTP routes. Each one hands the form to the controller and its answer to the presenter."""

import json
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from studio.l1_entities.errors import BackendBusy, Cancelled, InvalidJob, StudioError, UnreadableImage
from studio.l1_entities.video_job import VideoResult
from studio.l1_entities.voice_job import SpeechResult
from studio.l3_interface_adapters.api.json_api import JsonApi, rewrite_document
from studio.l3_interface_adapters.api.operations import OperationMissing
from studio.l3_interface_adapters.controllers.form_controller import FormController
from studio.l3_interface_adapters.controllers.video_controller import VideoController
from studio.l3_interface_adapters.presenters.html_presenter import HtmlPresenter

# Where the page's own files live. GET /page/<name> serves one of them, and a
# test points WEB at a directory of its own to reach both rules below.
WEB = Path(__file__).with_name("web").resolve()

# Only what a browser loads as code. The documents that sit beside them, this
# design among them, are not served.
PAGE_ASSETS = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
MAX_VIDEO_REQUEST_BYTES = 64 * 1024 * 1024


def make_handler(
    controller: FormController,
    presenter: HtmlPresenter,
    video_controller: VideoController | None = None,
    api: JsonApi | None = None,
) -> type[BaseHTTPRequestHandler]:
    class StudioHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            """Silence the access log. Prompts live in POST bodies, and none of
            this is wanted on disk or on the terminal."""

        def do_GET(self):
            path = urlsplit(self.path).path
            if path.startswith("/api/v1/"):
                self._api_get(path)
                return
            if path == "/":
                self._send(presenter.page(controller.page()))
            elif path == "/api/docs":
                self._send((WEB / "api-docs.html").read_text())
            elif self.path == "/progress":
                self._send(presenter.progress(controller.progress()))
            elif self.path == "/video/progress":
                self._send(presenter.video_progress(controller.progress()), content_type="application/json")
            elif self.path == "/rewrite/state":
                # The page polls this while a rewrite is in flight, so it is data
                # the page reads, not a fragment it appends.
                self._send(presenter.rewrite_state(controller.rewrite_state()), content_type="application/json")
            elif self.path.startswith("/page/"):
                self._send_page_asset(self.path.removeprefix("/page/"))
            else:
                self._send("not found", status=404, content_type="text/plain")

        def do_POST(self):
            if not self._from_this_page():
                self._send("forbidden", status=403, content_type="text/plain")
                return
            path = urlsplit(self.path).path
            if path.startswith("/api/v1/"):
                self._api_post(path)
                return
            if self.path == "/voice/operations":
                self._start_operation(source="ui")
                return
            if self.path == "/video/generate":
                self._run_video()
                return
            if self.path == "/video/cancel":
                self._cancel_video()
                return
            form = self._read_form()
            if self.path == "/generate":
                self._send(self._outcome(lambda: self._run_image_form(form)))
            elif self.path == "/cancel":
                api.cancel_image() if api else controller.cancel()
                self._send("", status=204, content_type="text/plain")
            elif self.path == "/backend":
                self._send(
                    self._outcome(lambda: (api.switch_backend(form, "image") if api else controller.switch(form)) or "")
                )
            elif self.path == "/video/backend":
                if video_controller is None:
                    self._send_json({"error": "Video generation is not configured."}, status=503)
                else:
                    self._send(
                        self._outcome(
                            lambda: (api.switch_backend(form, "video") if api else video_controller.switch(form)) or ""
                        )
                    )
            elif self.path == "/voice/backend":
                self._send(
                    self._outcome(lambda: api.switch_backend(form, "voice") or "")
                    if api
                    else "Voice generation is not configured."
                )
            elif self.path == "/workspace":
                self._send(self._outcome(lambda: (api.release_model() if api else controller.release_model()) or ""))
            elif self.path == "/rewrite":
                # The page reads this one as data, so a failure arrives as JSON
                # too. The other routes send HTML, which the page appends or toasts.
                self._send(
                    self._outcome(
                        lambda: presenter.rewrite(
                            api.observe(
                                "rewrite", form, lambda: controller.rewrite(form), rewrite_document, source="ui"
                            )
                            if api
                            else controller.rewrite(form)
                        ),
                        as_json=True,
                    ),
                    content_type="application/json",
                )
            elif self.path == "/rewrite/cancel":
                # The rewrite answers on its own request, so this one only asks for
                # the stop, the way `/cancel` does for a run.
                api.cancel_rewrite() if api else controller.cancel_rewrite()
                self._send("", status=204, content_type="text/plain")
            else:
                self._send("not found", status=404, content_type="text/plain")

        def _run_image_form(self, form) -> str:
            if api is None:
                return presenter.run(controller.run(form))
            result, operation = api.image_form_run(form)
            markup = presenter.run(result)
            attributes = f' data-operation-id="{operation["id"]}" data-operation-started="{operation["started_at"]}"'
            attributes += f' data-operation-completed="{operation["result_completed_at"]}"'
            return markup.replace('class="item', attributes + ' class="item', 1)

        def _api_get(self, path: str) -> None:
            if api is None:
                self._send_json({"error": "The JSON API is not configured."}, status=503)
                return
            readers = {
                "/api/v1/openapi.json": api.openapi,
                "/api/v1/studio": api.studio,
                "/api/v1/voice/capabilities": api.voice_capabilities,
                "/api/v1/progress": api.progress,
                "/api/v1/state": api.state,
                "/api/v1/rewrite/state": api.rewrite_state,
            }
            if (
                path.startswith(("/api/v1/images/backends/", "/api/v1/videos/backends/", "/api/v1/voice/backends/"))
                and path.count("/") == 5
            ):
                workspace = "voice" if "/voice/" in path else "image" if "/images/" in path else "video"
                body, status = self._api_result(lambda: api.backend_capabilities(workspace, path.rsplit("/", 1)[1]))
                self._send_json(body, status=status)
                return
            if path.startswith("/api/v1/operations/"):
                self._operation_get(path)
                return
            reader = readers.get(path)
            if reader is None:
                self._send_json({"error": "not found"}, status=404)
                return
            body, status = self._api_result(reader)
            self._send_json(body if body is not None else {}, status=status)

        def _api_post(self, path: str) -> None:
            """The API's own routes. A JSON body goes to the same controller the page
            uses, and every failure comes back as JSON with the status that names it."""
            if api is None:
                self._send_json({"error": "The JSON API is not configured."}, status=503)
                return
            if path == "/api/v1/audio/trim":
                result, status = self._api_result(lambda: api.trim_audio(self._read_json()))
                if status == 200:
                    audio, seconds = result
                    self._send_bytes(audio, content_type="audio/wav", headers={"X-Studio-Duration": str(seconds)})
                else:
                    self._send_json(result, status=status)
                return
            if path == "/api/v1/voice/generate":
                self._run_voice()
                return
            if path == "/api/v1/operations":
                self._start_operation()
                return
            if path.startswith("/api/v1/operations/") and path.endswith("/cancel"):
                operation_id = path.removeprefix("/api/v1/operations/").removesuffix("/cancel")
                body, status = self._api_result(lambda: api.cancel_operation(operation_id))
            elif path in ("/api/v1/images/backend", "/api/v1/videos/backend", "/api/v1/voice/backend"):
                workspace = "voice" if "/voice/" in path else "image" if "/images/" in path else "video"
                body, status = self._api_result(lambda: api.switch_backend(self._read_json(), workspace))
            elif path == "/api/v1/memory/release":
                body, status = self._api_result(api.release_model)
            elif path in ("/api/v1/images/generate", "/api/v1/images/edit"):
                mode = "edit" if path.endswith("edit") else "generate"
                body, status = self._api_result(lambda: api.image_run(self._read_json(), mode))
            elif path == "/api/v1/images/rewrite":
                body, status = self._api_result(lambda: api.image_rewrite(self._read_json()))
            elif path == "/api/v1/videos/rewrite":
                body, status = self._api_result(lambda: api.video_rewrite(self._read_json()))
            elif path == "/api/v1/images/cancel":
                body, status = self._api_result(api.cancel_image)
            elif path == "/api/v1/rewrite/cancel":
                body, status = self._api_result(api.cancel_rewrite)
            elif path == "/api/v1/videos/generate":
                self._run_video(mode="generate")
                return
            elif path == "/api/v1/videos/edit":
                self._run_video(mode="edit")
                return
            elif path == "/api/v1/videos/cancel":
                self._cancel_video(via_api=True)
                return
            else:
                self._send_json({"error": "not found"}, status=404)
                return
            if body is None:
                self._send("", status=204, content_type="text/plain")
            else:
                self._send_json(body, status=status)

        def _start_operation(self, source="api") -> None:
            assert api is not None
            payload = {}

            def reserve():
                payload.update(self._read_json())
                return api.reserve(payload, source=source)

            operation, status = self._api_result(reserve)
            if status != 200:
                self._send_json(operation, status=status)
                return
            threading.Thread(target=self._perform_operation, args=(operation, payload), daemon=True).start()
            self._send_json(operation, status=202, headers={"Location": operation["status_url"]})

        @staticmethod
        def _perform_operation(operation, payload) -> None:
            assert api is not None
            try:
                api.execute_operation(operation, payload)
            except Exception:
                # complete() records the failure for polling clients.
                return

        def _operation_get(self, path: str) -> None:
            assert api is not None
            suffix = path.removeprefix("/api/v1/operations/")
            if suffix.endswith("/result"):
                operation_id = suffix.removesuffix("/result")
                if "/items/" in operation_id:
                    owner, index = operation_id.split("/items/", 1)
                    result, status = self._api_result(lambda: api.item_result(owner, index))
                else:
                    result, status = self._api_result(lambda: api.operation_result(operation_id))
                if isinstance(result, VideoResult):
                    self._send_video_result(result)
                elif isinstance(result, SpeechResult):
                    self._send_voice_result(result)
                else:
                    self._send_json(result, status=status)
                return
            body, status = self._api_result(lambda: api.operation(suffix))
            self._send_json(body, status=status)

        def _run_voice(self):
            assert api is not None
            operation = {}

            def run():
                payload = self._read_json()
                operation.update(api.reserve({**payload, "kind": "voice"}))
                return api.execute_operation(operation, payload)

            result, status = self._api_result(run)
            if not isinstance(result, SpeechResult):
                self._send_json(result, status=status)
                return
            self._send_voice_result(
                result, {"X-Studio-Operation": operation["id"], "X-Studio-Completed": str(operation["finished_at"])}
            )

        def _send_voice_result(self, result, headers=None):
            headers = {
                **(headers or {}),
                "X-Studio-Seed": str(result.seed),
                "X-Studio-Duration": str(result.seconds),
                "X-Studio-Sample-Rate": str(result.sample_rate),
            }
            self._send_bytes(result.wav, content_type="audio/wav", headers=headers)

        def _send_video_result(self, result, headers: dict[str, str] | None = None) -> None:
            headers = dict(headers or {})
            if result.stub:
                self._send_json(
                    {
                        "stub": True,
                        "width": result.width,
                        "height": result.height,
                        "num_frames": result.num_frames,
                        "frame_rate": result.frame_rate,
                        "seed": result.seed,
                    },
                    headers=headers,
                )
            elif result.mp4 is None:
                self._send_json({"error": "The video backend returned no MP4 file."}, status=500)
            else:
                if result.seed is not None:
                    headers["X-Studio-Seed"] = str(result.seed)
                self._send_bytes(result.mp4, content_type="video/mp4", headers=headers)

        def _api_result(self, action) -> tuple[Any, int]:
            """One answer shape for every API route: the document and its status, or an
            error object and the status that names the failure."""
            try:
                return action(), 200
            except OperationMissing as error:
                return {"error": str(error)}, 404
            except Cancelled:
                return {"error": "Cancelled"}, 409
            except (InvalidJob, UnreadableImage) as error:
                return {"error": str(error)}, 400
            except BackendBusy as error:
                return {"error": str(error)}, 409
            except StudioError as error:
                return {"error": str(error)}, 503
            except Exception as error:
                return {"error": f"{type(error).__name__}: {error}"}, 500

        def _run_video(self, mode: str | None = None) -> None:
            if video_controller is None:
                self._send_json({"error": "Video generation is not configured."}, status=503)
                return
            try:
                payload = self._read_json()
                operation = (
                    api.reserve(
                        {**payload, "kind": "video", "mode": mode or payload.get("mode", "generate")},
                        source="ui" if mode is None else "api",
                    )
                    if api
                    else None
                )
                if operation is not None:
                    assert api is not None
                    if mode is None:
                        result = api.complete(
                            operation["id"], lambda: video_controller.run(payload), observed=operation
                        )
                    else:
                        result = api.execute_operation(operation, payload)
                else:
                    result = video_controller.run(payload)
            except Cancelled:
                self._send_json({"cancelled": True})
                return
            except (InvalidJob, UnreadableImage) as error:
                self._send_json({"error": str(error)}, status=400)
                return
            except BackendBusy as error:
                self._send_json({"error": str(error)}, status=409)
                return
            except StudioError as error:
                self._send_json({"error": str(error)}, status=503)
                return
            except Exception as error:
                self._send_json({"error": f"{type(error).__name__}: {error}"}, status=500)
                return
            headers = {"X-Studio-Operation": operation["id"]} if operation else None
            if headers is not None and operation is not None and operation.get("finished_at") is not None:
                headers["X-Studio-Completed"] = str(operation["finished_at"])
            self._send_video_result(result, headers)

        def _cancel_video(self, via_api: bool = False) -> None:
            if video_controller is None:
                self._send_json({"error": "Video generation is not configured."}, status=503)
                return
            try:
                payload = self._read_json()
                if via_api:
                    assert api is not None
                    cancelled = api.cancel_video(payload)
                else:
                    cancelled = video_controller.cancel(payload)
            except InvalidJob as error:
                self._send_json({"error": str(error)}, status=400)
                return
            if not cancelled:
                self._send_json({"error": "This video render is no longer active."}, status=409)
                return
            self._send("", status=204, content_type="text/plain")

        def _from_this_page(self) -> bool:
            """Any site open in the browser can post here. Its page sends its own
            Origin. With DNS rebinding its host name points here, and then its
            Host header names that site. So a POST must name this server in both."""
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://{host}":
                return False
            address = self.server.server_address
            if not isinstance(address, tuple):
                return False  # not a TCP server, so no host to compare
            bound, port = address[:2]
            if bound in ("0.0.0.0", "::"):
                return True  # every address of the machine is this server
            return host in (f"{bound}:{port}", f"[{bound}]:{port}", f"localhost:{port}")

        @staticmethod
        def _outcome(action, as_json: bool = False) -> str:
            try:
                return action()
            except Exception as error:  # every failure reaches the page as one line
                if as_json:
                    return json.dumps({"error": f"{type(error).__name__}: {error}"}, ensure_ascii=False)
                return presenter.failure(error)

        def _read_form(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            form = {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}
            form["client_id"] = self.headers.get("X-Studio-Client", "")
            form["library_id"] = self.headers.get("X-Studio-Library", "")
            return form

        def _read_json(self) -> dict:
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                raise InvalidJob("The video request must use application/json")
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= MAX_VIDEO_REQUEST_BYTES:
                raise InvalidJob("The video request size must be between 1 byte and 64 MB")
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise InvalidJob("The video request must contain valid JSON") from None
            if not isinstance(payload, dict):
                raise InvalidJob("The video request must be a JSON object")
            payload["client_id"] = self.headers.get("X-Studio-Client") or payload.get("client_id", "")
            payload["library_id"] = self.headers.get("X-Studio-Library") or payload.get("library_id", "")
            return payload

        def _send_page_asset(self, name: str) -> None:
            """One module or stylesheet out of web/. Two rules keep it to those:
            the resolved path stays inside web/, so `..` cannot escape it, and
            only .js and .css are handed out. Without both, every document in
            that directory would be readable."""
            asset = (WEB / name).resolve()
            if not asset.is_relative_to(WEB) or asset.suffix not in PAGE_ASSETS or not asset.is_file():
                self._send("not found", status=404, content_type="text/plain")
                return
            self._send(asset.read_text(encoding="utf-8"), content_type=PAGE_ASSETS[asset.suffix])

        def _send(self, body: str, status: int = 200, content_type: str = "text/html; charset=utf-8"):
            self._send_bytes(body.encode("utf-8"), status, content_type)

        def _send_json(self, payload: dict, status: int = 200, headers: dict[str, str] | None = None) -> None:
            self._send_bytes(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                status,
                "application/json; charset=utf-8",
                headers,
            )

        def _send_bytes(
            self,
            payload: bytes,
            status: int = 200,
            content_type: str = "application/octet-stream",
            headers: dict[str, str] | None = None,
        ):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            # The studio serves files that change between restarts, and it sent no cache
            # header at all, so a browser was free to keep an old page.css or module and show
            # a form the server no longer had. Nothing here is worth caching.
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

    return StudioHandler
