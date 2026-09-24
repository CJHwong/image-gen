"""The HTTP routes. Each one hands the form to the controller and its answer to the presenter."""

from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs

from studio.l3_interface_adapters.controllers.form_controller import FormController
from studio.l3_interface_adapters.presenters.html_presenter import HtmlPresenter


def make_handler(controller: FormController, presenter: HtmlPresenter) -> type[BaseHTTPRequestHandler]:
    class StudioHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            """Silence the access log. Prompts live in POST bodies, and none of
            this is wanted on disk or on the terminal."""

        def do_GET(self):
            if self.path == "/":
                self._send(presenter.page(controller.page()))
            elif self.path == "/progress":
                self._send(presenter.progress(controller.progress()))
            else:
                self._send("not found", status=404, content_type="text/plain")

        def do_POST(self):
            if not self._from_this_page():
                self._send("forbidden", status=403, content_type="text/plain")
                return
            form = self._read_form()
            if self.path == "/generate":
                self._send(self._outcome(lambda: presenter.run(controller.run(form))))
            elif self.path == "/cancel":
                controller.cancel()
                self._send("", status=204, content_type="text/plain")
            elif self.path == "/backend":
                self._send(self._outcome(lambda: controller.switch(form) or ""))
            else:
                self._send("not found", status=404, content_type="text/plain")

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
        def _outcome(action) -> str:
            try:
                return action()
            except Exception as error:  # every failure reaches the page as one line
                return presenter.failure(error)

        def _read_form(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            return {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}

        def _send(self, body: str, status: int = 200, content_type: str = "text/html; charset=utf-8"):
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return StudioHandler
