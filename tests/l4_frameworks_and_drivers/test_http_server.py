"""The HTTP routes: a form goes to the controller, the answer goes to the presenter."""

import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from studio.l1_entities.errors import BackendBusy, StudioError
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l3_interface_adapters.gateways.prompt_rewriters import StubPromptRewriter
from studio.l4_frameworks_and_drivers import http_server
from studio.l4_frameworks_and_drivers.main import assemble_studio
from tests.support.fakes import FakeBackendGateway, FakeVideoBackendGateway


def fast(rewriter):
    """Set the stub's two clocks to zero on the instance, so a route answers at once."""
    rewriter.PREPARING_SECONDS = 0
    rewriter.WRITING_SLICE_SECONDS = 0
    return rewriter


class FakeVideoBackend(FakeVideoBackendGateway):
    def __init__(self):
        super().__init__("video-fake", "Fake video")
        self.failure = None
        self.result = None

    def run(self, job: VideoJob, progress=None) -> VideoResult:
        self.jobs.append(job)
        if self.failure is not None:
            raise self.failure
        if progress:
            progress(4, 8, 1)
        if self.result is not None:
            return self.result
        return VideoResult(b"fake mp4 bytes", job.width, job.height, job.num_frames, job.frame_rate, job.seed)


@pytest.fixture
def served():
    """A real server on a free port over two fake backends, so a route runs for real.

    The stub's rewriter sleeps while it writes, so the fixture sets the stub's two
    clocks to zero. A route test reads status and body, and never the clock.
    """
    backends = {"fake": FakeBackendGateway(), "other": FakeBackendGateway("other", "Other")}
    rewriters = {name: fast(StubPromptRewriter()) for name in backends}
    video_backend = FakeVideoBackend()
    other_video = FakeVideoBackendGateway("video-other", "Other video")
    studio = assemble_studio(
        backends,
        rewriters,
        "fake",
        ("fake", "other"),
        video_backends={"video-fake": video_backend, "video-other": other_video},
        default_video_id="video-fake",
        visible_video_ids=("video-fake", "video-other"),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server, video_backend, other_video
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


def test_the_root_route_keeps_the_selected_workspace_in_the_url(served):
    status, content_type, body = call(served[1], "/?workspace=video")

    assert status == 200 and content_type == "text/html; charset=utf-8"
    assert '"video": {"backend": {"id": "video-fake"' in body


def test_the_progress_route_hands_back_the_next_poll(served):
    """The poller clocks itself: every progress answer carries the request that asks again."""
    status, _, body = call(served[1], "/progress")
    assert status == 200 and 'hx-get="/progress" hx-trigger="load delay:800ms"' in body


def test_the_video_progress_route_returns_json(served):
    status, content_type, body = call(served[1], "/video/progress")

    assert status == 200 and content_type == "application/json"
    assert json.loads(body) == {"running": False, "stage": "", "step": 0, "total": 0, "phase": 0, "kind": ""}


def test_a_get_to_an_unknown_path_is_a_plain_not_found(served):
    status, content_type, body = call(served[1], "/nope")
    assert (status, content_type, body) == (404, "text/plain", "not found")


def test_a_page_script_is_served_from_the_page_directory(served, tmp_path, monkeypatch):
    """The page loads its modules through this route, so it hands back the file's
    own bytes with the type a browser runs as code. The modules live in
    subdirectories of their own, so a name keeps its path."""
    root = tmp_path / "web"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "state.js").write_text("export const one = 1;\n", encoding="utf-8")
    monkeypatch.setattr(http_server, "WEB", root)
    status, content_type, body = call(served[1], "/page/lib/state.js")
    assert (status, content_type, body) == (200, "text/javascript; charset=utf-8", "export const one = 1;\n")


def test_the_page_stylesheet_is_served_from_the_page_directory(served):
    """The page holds no CSS of its own, so this one fetch is the whole of how it
    looks. The stylesheet's own type, and many rules inside it, or the page is bare."""
    status, content_type, body = call(served[1], "/page/page.css")
    assert (status, content_type) == (200, "text/css; charset=utf-8")
    assert body.count("{") > 100


def test_a_traversal_out_of_the_page_directory_is_refused(served, tmp_path, monkeypatch):
    """A name is not a path. `..` resolves above the directory the route serves
    from, and a stylesheet that lives there must not go out."""
    root = tmp_path / "web"
    root.mkdir()
    (tmp_path / "outside.css").write_text("body { color: red; }\n", encoding="utf-8")
    monkeypatch.setattr(http_server, "WEB", root)
    assert call(served[1], "/page/../outside.css") == (404, "text/plain", "not found")


def test_the_page_directory_does_not_hand_out_its_own_documents(served):
    """PAGE-REFACTOR.md sits beside the assets. It is the design for the page, and
    the browser never loads it."""
    assert call(served[1], "/page/PAGE-REFACTOR.md") == (404, "text/plain", "not found")


def test_a_page_asset_that_is_not_there_is_a_plain_not_found(served):
    assert call(served[1], "/page/absent.css") == (404, "text/plain", "not found")


def video_request(**updates):
    payload = {
        "prompt": "A kite rises",
        "width": 960,
        "height": 544,
        "num_frames": 145,
        "frame_rate": 24,
        "seed": 42,
        "references": [],
    }
    payload.update(updates)
    return json.dumps(payload).encode()


def post_video(server, body):
    return call(server, "/video/generate", body, **{"Content-Type": "application/json"})


def post_video_with_length(server, body, length):
    url = f"http://127.0.0.1:{server.server_address[1]}/video/generate"
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Content-Length": str(length)},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.status, answer.headers["Content-Type"], answer.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.headers["Content-Type"], error.read().decode()


def test_video_route_returns_mp4_bytes_from_the_backend(served):
    status, content_type, body = post_video(served[1], video_request())

    assert (status, content_type, body) == (200, "video/mp4", "fake mp4 bytes")
    assert served[2].jobs[0].prompt == "A kite rises"


def test_video_stub_route_returns_metadata_only(served):
    served[2].result = VideoResult(None, 768, 768, 145, 24, None, stub=True)

    status, content_type, body = post_video(served[1], video_request(width=768, height=768, seed=None))

    assert status == 200 and content_type == "application/json; charset=utf-8"
    assert json.loads(body) == {
        "stub": True,
        "width": 768,
        "height": 768,
        "num_frames": 145,
        "frame_rate": 24,
        "seed": None,
    }


def test_video_route_rejects_invalid_json_and_wrong_content_type(served):
    invalid_json = call(served[1], "/video/generate", b"not json", **{"Content-Type": "application/json"})
    wrong_type = call(served[1], "/video/generate", b"{}", **{"Content-Type": "text/plain"})

    assert invalid_json[0] == 400
    assert json.loads(invalid_json[2])["error"] == "The video request must contain valid JSON"
    assert wrong_type[0] == 400
    assert "application/json" in json.loads(wrong_type[2])["error"]


@pytest.mark.parametrize(
    ("body", "headers", "length", "message"),
    [
        (b"", {"Content-Type": "application/json"}, None, "between 1 byte and 64 MB"),
        (b"\xff", {"Content-Type": "application/json"}, None, "valid JSON"),
        (b"[]", {"Content-Type": "application/json"}, None, "JSON object"),
        (b"{}", {}, None, "application/json"),
    ],
)
def test_video_route_rejects_invalid_request_shapes(served, body, headers, length, message):
    if length is None:
        response = call(served[1], "/video/generate", body, **headers)
    else:
        response = post_video_with_length(served[1], body, length)

    assert response[0] == 400 and message in json.loads(response[2])["error"]


def test_video_route_rejects_an_oversized_body_before_reading_it(served):
    response = post_video_with_length(served[1], b"x", 64 * 1024 * 1024 + 1)

    assert response[0] == 400
    assert "between 1 byte and 64 MB" in json.loads(response[2])["error"]


@pytest.mark.parametrize(
    ("video_body", "message"),
    [
        (video_request(prompt=" "), "A video prompt is required."),
        (
            video_request(references=[{"name": "broken", "image": "bad", "frame_index": 0, "strength": 1}]),
            "Could not read that video reference image.",
        ),
    ],
)
def test_video_route_returns_controller_errors_as_bad_requests(served, video_body, message):
    response = post_video(served[1], video_body)

    assert response[0] == 400 and json.loads(response[2])["error"] == message


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (BackendBusy("The model is busy"), 409),
        (StudioError("local weights are missing"), 503),
        (RuntimeError("pipeline failed"), 500),
    ],
)
def test_video_route_reports_pipeline_errors_as_json(served, failure, status):
    served[2].failure = failure

    response = post_video(served[1], video_request())

    assert response[0] == status and json.loads(response[2])["error"]


def test_video_route_rejects_a_video_result_without_mp4_bytes(served):
    served[2].result = VideoResult(None, 960, 544, 145, 24, None)

    response = post_video(served[1], video_request(seed=None))

    assert response[0] == 500
    assert json.loads(response[2])["error"] == "The video backend returned no MP4 file."


def test_video_model_route_changes_only_the_video_selection(served):
    status, _, body = call(served[1], "/video/backend", b"backend=video-other")
    page_status, _, page = call(served[1], "/")

    assert status == 200 and body == ""
    assert page_status == 200 and '"id": "video-other"' in page
    assert served[0].catalog.active_id() == "fake"
    assert served[0].video_catalog.active_id() == "video-other"
    assert served[3].jobs == []


def test_workspace_route_releases_the_resident_model(served):
    image_status, _, _ = call(served[1], "/generate", b"prompt=a cat&steps=1")
    release_status, _, release_body = call(served[1], "/workspace", b"workspace=video")

    assert image_status == 200 and release_status == 200 and release_body == ""
    assert served[0].residency.active_id() is None
    assert served[0].catalog.get("fake")._backend.events == ["release"]


def test_video_route_is_unavailable_without_a_video_backend():
    backends = {"fake": FakeBackendGateway()}
    rewriters = {"fake": fast(StubPromptRewriter())}
    studio = assemble_studio(backends, rewriters, "fake", ("fake",))
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        response = post_video(server, video_request())
    finally:
        server.shutdown()
        server.server_close()

    assert response[0] == 503
    assert json.loads(response[2])["error"] == "Video generation is not configured."


def test_video_model_switch_is_unavailable_without_a_video_backend():
    backends = {"fake": FakeBackendGateway()}
    rewriters = {"fake": fast(StubPromptRewriter())}
    studio = assemble_studio(backends, rewriters, "fake", ("fake",))
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        response = call(server, "/video/backend", b"backend=ltx25")
    finally:
        server.shutdown()
        server.server_close()

    assert response[0] == 503
    assert json.loads(response[2])["error"] == "Video generation is not configured."


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


def test_the_rewrite_state_route_answers_the_three_fields_the_page_reads(served):
    """The page polls this while a rewrite is in flight, so it is JSON and not a
    fragment. With nothing in flight it reports the idle state."""
    status, content_type, body = call(served[1], "/rewrite/state")
    assert status == 200 and content_type == "application/json"
    assert json.loads(body) == {"running": False, "stage": "idle", "stopping": False}


def test_the_rewrite_cancel_route_answers_with_no_content(served):
    """The stop is a flag the rewriter reads, so the route reports nothing back."""
    assert call(served[1], "/rewrite/cancel", b"") == (204, "text/plain", "")


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
