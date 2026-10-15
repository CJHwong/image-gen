"""The HTTP routes. Each one hands the form to the controller and its answer to the presenter."""

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from studio.l1_entities.errors import BackendBusy, InvalidJob, StudioError, UnreadableImage
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
) -> type[BaseHTTPRequestHandler]:
    class StudioHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            """Silence the access log. Prompts live in POST bodies, and none of
            this is wanted on disk or on the terminal."""

        def do_GET(self):
            if urlsplit(self.path).path == "/":
                self._send(presenter.page(controller.page()))
            elif self.path == "/progress":
                self._send(presenter.progress(controller.progress()))
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
            if self.path == "/video/generate":
                self._run_video()
                return
            form = self._read_form()
            if self.path == "/generate":
                self._send(self._outcome(lambda: presenter.run(controller.run(form))))
            elif self.path == "/cancel":
                controller.cancel()
                self._send("", status=204, content_type="text/plain")
            elif self.path == "/backend":
                self._send(self._outcome(lambda: controller.switch(form) or ""))
            elif self.path == "/video/backend":
                if video_controller is None:
                    self._send_json({"error": "Video generation is not configured."}, status=503)
                else:
                    self._send(self._outcome(lambda: video_controller.switch(form) or ""))
            elif self.path == "/workspace":
                self._send(self._outcome(lambda: controller.release_model() or ""))
            elif self.path == "/rewrite":
                # The page reads this one as data, so a failure arrives as JSON
                # too. The other routes send HTML, which the page appends or toasts.
                self._send(
                    self._outcome(lambda: presenter.rewrite(controller.rewrite(form)), as_json=True),
                    content_type="application/json",
                )
            elif self.path == "/rewrite/cancel":
                # The rewrite answers on its own request, so this one only asks for
                # the stop, the way `/cancel` does for a run.
                controller.cancel_rewrite()
                self._send("", status=204, content_type="text/plain")
            else:
                self._send("not found", status=404, content_type="text/plain")

        def _run_video(self) -> None:
            if video_controller is None:
                self._send_json({"error": "Video generation is not configured."}, status=503)
                return
            try:
                result = video_controller.run(self._read_json())
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
            if result.stub:
                self._send_json(
                    {
                        "stub": True,
                        "width": result.width,
                        "height": result.height,
                        "num_frames": result.num_frames,
                        "frame_rate": result.frame_rate,
                        "seed": result.seed,
                    }
                )
            elif result.mp4 is None:
                self._send_json({"error": "The video backend returned no MP4 file."}, status=500)
            else:
                self._send_bytes(result.mp4, content_type="video/mp4")

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
            return {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}

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

        def _send_json(self, payload: dict, status: int = 200) -> None:
            self._send(json.dumps(payload, ensure_ascii=False), status, "application/json; charset=utf-8")

        def _send_bytes(self, payload: bytes, status: int = 200, content_type: str = "application/octet-stream"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return StudioHandler
