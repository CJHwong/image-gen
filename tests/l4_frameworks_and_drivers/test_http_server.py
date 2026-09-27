"""The HTTP routes: a form goes to the controller, the answer goes to the presenter."""

import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from studio.l3_interface_adapters.gateways.prompt_rewriters import StubPromptRewriter
from studio.l4_frameworks_and_drivers.main import assemble_studio
from tests.support.fakes import FakeBackendGateway


@pytest.fixture
def served():
    """A real server on a free port over two fake backends, so a route runs for real."""
    backends = {"fake": FakeBackendGateway(), "other": FakeBackendGateway("other", "Other")}
    studio = assemble_studio(backends, {name: StubPromptRewriter() for name in backends}, "fake", ("fake", "other"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server
    server.shutdown()
    server.server_close()


def call(server, path, body=None, **headers):
    """One request, answered as (status, content type, body)."""
    url = f"http://127.0.0.1:{server.server_address[1]}{path}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.status, answer.headers["Content-Type"], answer.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.headers["Content-Type"], error.read().decode()


def test_the_root_route_serves_the_page(served):
    status, content_type, body = call(served[1], "/")
    assert status == 200 and content_type == "text/html; charset=utf-8"
    assert "<title>Fake</title>" in body and '<input type="hidden" name="backend" value="fake">' in body


def test_the_progress_route_hands_back_the_next_poll(served):
    """The poller clocks itself: every progress answer carries the request that asks again."""
    status, _, body = call(served[1], "/progress")
    assert status == 200 and 'hx-get="/progress" hx-trigger="load delay:800ms"' in body


def test_a_get_to_an_unknown_path_is_a_plain_not_found(served):
    status, content_type, body = call(served[1], "/nope")
    assert (status, content_type, body) == (404, "text/plain", "not found")


def test_a_generate_route_answers_with_the_image_fragment(served):
    status, _, body = call(served[1], "/generate", b"prompt=a cat&steps=3&seed=7")
    assert status == 200 and base64.b64encode(b"png").decode() in body and 'data-mode="generate"' in body


def test_a_form_the_engine_refuses_arrives_as_one_error_line(served):
    """A bad form value is the page's fault, not the server's, so it answers 200
    with a fragment the page can show."""
    status, _, body = call(served[1], "/generate", b"prompt=a cat&count=two")
    assert status == 200 and body == '<div class="err">Bad form value: count must be a whole number</div>'


def test_the_cancel_route_answers_with_no_content(served):
    assert call(served[1], "/cancel", b"")[:2] == (204, "text/plain")


def test_the_backend_route_switches_the_page_to_the_other_backend(served):
    status, _, body = call(served[1], "/backend", b"backend=other")
    assert (status, body) == (200, "")
    assert "<title>Other</title>" in call(served[1], "/")[2]


def test_the_rewrite_route_answers_as_json(served):
    """The page reads this one into the prompt box, so it is data and not a fragment."""
    status, content_type, body = call(served[1], "/rewrite", b"prompt=a cat&mode=generate")
    assert status == 200 and content_type == "application/json"
    assert json.loads(body) == {
        "prompt": "a cat A longer version of it, written for the stub.",
        "size": None,
        "elapsed": 0.0,
    }


def test_a_failed_rewrite_is_json_too(served):
    """The other routes send HTML. This one has to send JSON even when it fails,
    or the page would read an error fragment as a prompt."""
    status, content_type, body = call(served[1], "/rewrite", b"prompt=&mode=generate")
    assert status == 200 and content_type == "application/json"
    assert json.loads(body)["error"] == "InvalidJob: Write something to rewrite first."


def test_a_post_to_an_unknown_path_is_a_plain_not_found(served):
    assert call(served[1], "/nope", b"") == (404, "text/plain", "not found")


def test_a_post_from_another_site_is_refused(served):
    """Any page open in the browser can post here, so the Origin and the Host
    both have to name this server."""
    server = served[1]
    own = f"http://127.0.0.1:{server.server_address[1]}"
    assert call(server, "/cancel", b"", Origin=own)[0] == 204
    assert call(server, "/cancel", b"")[0] == 204  # no Origin: not a browser page
    assert call(server, "/cancel", b"", Origin="http://evil.example")[0] == 403
    assert call(server, "/cancel", b"", Host=f"evil.example:{server.server_address[1]}")[0] == 403


def from_this_page(studio, address, host):
    """The handler's own check, against a server address I choose.

    A ThreadingHTTPServer always has a (host, port) address, so the branches for
    another shape are reached with a stand-in instead of a socket.
    """
    handler = SimpleNamespace(headers={"Host": host}, server=SimpleNamespace(server_address=address))
    return studio.handler._from_this_page(handler)


def test_a_server_on_every_address_accepts_any_host(served):
    """`--host 0.0.0.0` serves every address of the machine, so every host name
    the browser could have reached it by is this server."""
    assert from_this_page(served[0], ("0.0.0.0", 8765), "192.168.1.4:8765") is True
    assert from_this_page(served[0], ("::", 8765), "[::1]:8765") is True


def test_a_server_with_no_tcp_address_refuses_the_post(served):
    """A unix socket server has no host and port to compare, so nothing proves
    the POST came from this page."""
    assert from_this_page(served[0], "/tmp/studio.sock", "localhost:8765") is False


def test_only_the_bound_names_accept_the_post(served):
    """With DNS rebinding a foreign page reaches this port while its own host
    name sits in the Host header, so that name has to fail the check."""
    port = served[1].server_address[1]
    assert from_this_page(served[0], ("127.0.0.1", port), f"127.0.0.1:{port}") is True
    assert from_this_page(served[0], ("127.0.0.1", port), f"localhost:{port}") is True
    assert from_this_page(served[0], ("127.0.0.1", port), f"evil.example:{port}") is False
