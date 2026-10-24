"""The HTTP routes: a form goes to the controller, the answer goes to the presenter."""

import base64
import json
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any, cast

import pytest

from studio.l1_entities.errors import BackendBusy, Cancelled, StudioError
from studio.l1_entities.video_capabilities import VideoAdapter, VideoMode
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l3_interface_adapters.gateways.prompt_rewriters import StubPromptRewriter
from studio.l4_frameworks_and_drivers import http_server
from studio.l4_frameworks_and_drivers.main import assemble_studio
from tests.support.fakes import FakeBackendGateway, FakeVideoBackendGateway, fake_video_capabilities


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

    def run(self, job: VideoJob, progress=None, cancelled=None) -> VideoResult:
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


def test_every_response_forbids_a_stale_copy(served):
    """The page, its modules and its stylesheet are files that change with the tree, and they
    shipped with no cache header at all. A browser was then free to keep an old page.css across
    a restart and draw a form the server no longer had, which read as a fix that never landed."""
    url = f"http://127.0.0.1:{served[1].server_address[1]}"
    for path in ("/", "/page/page.css", "/page/components/run-button.js", "/progress"):
        with urllib.request.urlopen(url + path, timeout=30) as answer:
            assert answer.headers["Cache-Control"] == "no-store", path


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
    assert json.loads(body) == {
        "running": False,
        "stage": "",
        "step": 0,
        "total": 0,
        "phase": 0,
        "kind": "",
        "stopping": False,
        "request_id": None,
    }


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
        "request_id": "run-a",
        "references": [],
    }
    payload.update(updates)
    return json.dumps(payload).encode()


def post_video(server, body):
    return call(server, "/video/generate", body, **{"Content-Type": "application/json"})


def post_video_cancel(server, request_id):
    body = json.dumps({"request_id": request_id}).encode()
    return call(server, "/video/cancel", body, **{"Content-Type": "application/json"})


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
    url = f"http://127.0.0.1:{served[1].server_address[1]}/video/generate"
    request = urllib.request.Request(
        url,
        data=video_request(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as answer:
        status, content_type, body = answer.status, answer.headers["Content-Type"], answer.read().decode()
        seed = answer.headers.get("X-Studio-Seed")
        completed_at = float(answer.headers["X-Studio-Completed"])

    assert (status, content_type, body) == (200, "video/mp4", "fake mp4 bytes")
    assert seed == "42"
    assert served[2].jobs[0].prompt == "A kite rises"
    _, _, state = call(served[1], "/api/v1/state")
    assert completed_at == json.loads(state)["operations"][0]["finished_at"]


def test_video_route_returns_cancellation_as_a_successful_result(served):
    served[2].failure = Cancelled("video generation was cancelled")

    status, content_type, body = post_video(served[1], video_request())

    assert status == 200 and content_type == "application/json; charset=utf-8"
    assert json.loads(body) == {"cancelled": True}


def test_video_cancel_only_stops_the_matching_request(served):
    entered = threading.Event()
    waiting = threading.Event()
    result = []

    def wait_for_cancel(job, progress=None, cancelled=None):
        assert cancelled is not None
        entered.set()
        while not cancelled():
            waiting.wait(0.01)
        raise Cancelled("video generation was cancelled")

    served[2].run = wait_for_cancel
    worker = threading.Thread(target=lambda: result.append(post_video(served[1], video_request(request_id="run-a"))))
    worker.start()
    assert entered.wait(5)

    progress = json.loads(call(served[1], "/video/progress")[2])
    wrong_request = post_video_cancel(served[1], "run-b")
    legacy_cancel = call(served[1], "/cancel", b"")
    progress_after_legacy_cancel = json.loads(call(served[1], "/video/progress")[2])
    matching_request = post_video_cancel(served[1], "run-a")
    worker.join(timeout=5)
    inactive_request = post_video_cancel(served[1], "run-a")

    assert progress["request_id"] == "run-a"
    assert wrong_request[0] == 409
    assert legacy_cancel[0] == 204
    assert progress_after_legacy_cancel["running"] is True
    assert progress_after_legacy_cancel["stopping"] is False
    assert matching_request[0] == 204
    assert not worker.is_alive()
    assert result[0][0] == 200 and json.loads(result[0][2]) == {"cancelled": True}
    assert inactive_request[0] == 409


def test_video_cancel_rejects_a_request_without_an_id(served):
    response = call(served[1], "/video/cancel", b"{}", **{"Content-Type": "application/json"})

    assert response[0] == 400
    assert "request_id" in json.loads(response[2])["error"]


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
        cancel_response = post_video_cancel(server, "run-a")
    finally:
        server.shutdown()
        server.server_close()

    assert response[0] == 503
    assert json.loads(response[2])["error"] == "Video generation is not configured."
    assert cancel_response[0] == 503
    assert json.loads(cancel_response[2])["error"] == "Video generation is not configured."


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


def test_an_allowed_origin_posts_through_a_proxy():
    """Tailscale serve gives the page an https origin and a host name that this
    server did not bind, so only an origin named at the start lets it post."""
    proxy = "https://my-mac.example.ts.net:8765"
    handler = cast(Any, http_server.make_handler(cast(Any, None), cast(Any, None), allowed_origins=(proxy,)))

    def posts(origin, host="my-mac.example.ts.net:8765"):
        headers = {"Host": host} if origin is None else {"Host": host, "Origin": origin}
        request = SimpleNamespace(headers=headers, server=SimpleNamespace(server_address=("127.0.0.1", 8765)))
        return handler._from_this_page(request)

    assert posts(proxy) is True
    assert posts("http://my-mac.example.ts.net:8765") is False  # the host is not one this server bound
    assert posts("https://evil.example") is False
    # The list opens the Origin check only: the proxy's host name alone proves nothing.
    assert posts(None) is False
    # The page on the bound address keeps the rule it had before the list.
    assert posts("http://127.0.0.1:8765", host="127.0.0.1:8765") is True


# ---- The JSON API -----------------------------------------------------------
# The routes the page does not use. They ride the same controller, so these
# tests check the transport and the document, not a second set of rules.
def post_json(server, path, payload=None):
    body = json.dumps(payload if payload is not None else {}).encode()
    return call(server, path, body, **{"Content-Type": "application/json"})


def test_the_studio_route_names_the_models_and_their_modes(served):
    status, content_type, body = call(served[1], "/api/v1/studio")
    document = json.loads(body)

    assert status == 200 and content_type == "application/json; charset=utf-8"
    assert document["image"]["active"] == "fake"
    assert [mode["id"] for mode in document["image"]["capabilities"]["modes"]] == ["generate", "edit"]
    assert document["video"]["active"] == "video-fake"


def test_the_image_route_answers_every_image_of_the_batch_as_json(served):
    status, content_type, body = post_json(
        served[1],
        "/api/v1/images/generate",
        {"prompt": "a pear", "count": 2, "seed": 4},
    )
    document = json.loads(body)

    assert status == 200 and content_type == "application/json; charset=utf-8"
    assert [image["seed"] for image in document["images"]] == [4, 5]
    assert base64.b64decode(document["images"][0]["png_base64"]) == b"png"
    assert document["images"][0]["prompt"] == "a pear"


def test_the_edit_route_needs_a_reference(served):
    status, _, body = post_json(served[1], "/api/v1/images/edit", {"prompt": "make it blue"})

    assert status == 400
    assert "reference" in json.loads(body)["error"]


def test_the_image_rewrite_route_answers_the_longer_words(served):
    status, _, body = post_json(served[1], "/api/v1/images/rewrite", {"prompt": "a pear"})

    assert status == 200
    assert json.loads(body)["prompt"]


def test_the_video_rewrite_route_is_the_video_workspace_of_the_same_rewriter(served):
    status, _, body = post_json(served[1], "/api/v1/videos/rewrite", {"prompt": "a clip"})

    assert status == 200
    assert json.loads(body)["prompt"]


def test_the_progress_route_reads_the_run_in_flight(served):
    status, _, body = call(served[1], "/api/v1/progress")

    assert status == 200
    assert json.loads(body)["running"] is False


def test_the_cancel_routes_answer_no_content(served):
    assert post_json(served[1], "/api/v1/images/cancel")[0] == 204
    assert post_json(served[1], "/api/v1/rewrite/cancel")[0] == 204


def test_the_video_generate_route_returns_the_mp4(served):
    url = f"http://127.0.0.1:{served[1].server_address[1]}/api/v1/videos/generate"
    request = urllib.request.Request(
        url,
        data=video_request(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as answer:
        assert answer.status == 200
        assert answer.headers["Content-Type"] == "video/mp4"
        assert answer.headers["X-Studio-Seed"] == "42"
        assert answer.read() == b"fake mp4 bytes"


def test_the_video_routes_fix_the_mode_they_name(served):
    """Both routes carry the same body. The generate route runs it, and the edit route
    reads the same body as an edit and asks for the clip the mode needs."""
    served[2]._capabilities = replace(
        fake_video_capabilities(),
        modes=(VideoMode("generate", "Generate"), VideoMode("edit", "Edit", needs_clip=True)),
        adapters=(VideoAdapter(id="day", label="Day", hint="", mode="edit", file="a.safetensors"),),
    )

    status, _, _ = post_json(served[1], "/api/v1/videos/generate", json.loads(video_request()))
    assert status == 200
    edit_status, _, edit_body = post_json(served[1], "/api/v1/videos/edit", json.loads(video_request()))

    # Only an edit asks for an adapter, so the message is the proof the mode was read.
    assert edit_status == 400
    assert json.loads(edit_body)["error"] == "adapter must be one of day"


def test_a_video_stop_without_a_request_id_is_a_bad_request(served):
    status, _, body = post_json(served[1], "/api/v1/videos/cancel", {})

    assert status == 400
    assert "no video render" in json.loads(body)["error"].lower()


def test_an_unknown_api_route_is_a_json_not_found(served):
    status, content_type, body = call(served[1], "/api/v1/nothing")

    assert status == 404 and content_type == "application/json; charset=utf-8"
    assert json.loads(body) == {"error": "not found"}


def test_api_docs_renders_the_existing_spec_and_keeps_a_raw_link(served):
    status, content_type, body = call(served[1], "/api/docs")

    assert status == 200
    assert content_type == "text/html; charset=utf-8"
    assert 'id="swagger-ui"' in body
    assert 'url: "/api/v1/openapi.json"' in body
    assert 'href="/api/v1/openapi.json"' in body
    assert "validatorUrl: null" in body
    assert "filter: true" in body


def test_every_documented_path_is_a_route_this_server_serves(served):
    """The spec is written by hand, so this walks it: a path the document names and
    the server does not serve would be a promise the API does not keep."""
    _, _, body = call(served[1], "/api/v1/openapi.json")
    document = json.loads(body)

    assert document["openapi"].startswith("3.")
    post_json(served[1], "/api/v1/images/generate", {"prompt": "pear"})
    _, _, state = call(served[1], "/api/v1/state")
    operation_id = json.loads(state)["operations"][0]["id"]
    for path, operations in document["paths"].items():
        backend_id = "fake" if "/images/" in path else "video-fake"
        path = path.replace("{id}", backend_id if "/backends/" in path else operation_id)
        for method in operations:
            if method == "get":
                status, _, _ = call(served[1], path)
            else:
                status, _, _ = post_json(served[1], path)
            assert status != 404, f"{method.upper()} {path} is documented but not served"


def test_the_api_reports_a_busy_gpu_as_conflict(served):
    served[0].catalog.get("fake")._backend.fail_with = BackendBusy("The model is busy")

    status, _, body = post_json(served[1], "/api/v1/images/generate", {"prompt": "a pear"})

    assert status == 409
    assert "error" in json.loads(body)


def test_the_api_reports_a_pipeline_error_as_unavailable(served):
    served[0].video_catalog.get("video-fake").failure = StudioError("the engine is missing")

    status, _, body = post_json(served[1], "/api/v1/videos/generate", json.loads(video_request()))

    assert status == 503
    assert json.loads(body)["error"] == "the engine is missing"


def test_the_api_reports_an_unexpected_error_as_a_server_error(served):
    served[0].video_catalog.get("video-fake").failure = ValueError("boom")

    status, _, body = post_json(served[1], "/api/v1/videos/generate", json.loads(video_request()))

    assert status == 500
    assert json.loads(body)["error"] == "ValueError: boom"


def test_an_unknown_api_post_is_a_json_not_found(served):
    status, _, body = post_json(served[1], "/api/v1/nothing", {})

    assert status == 404
    assert json.loads(body) == {"error": "not found"}


def test_the_api_reports_a_stopped_run_as_conflict(served):
    served[0].catalog.get("fake")._backend.fail_with = Cancelled("stopped at step 2")

    status, _, body = post_json(served[1], "/api/v1/images/generate", {"prompt": "a pear"})

    assert status == 409
    assert json.loads(body) == {"error": "Cancelled"}


def test_the_api_reports_an_unexpected_image_error_as_a_server_error(served):
    served[0].catalog.get("fake")._backend.fail_with = ValueError("boom")

    status, _, body = post_json(served[1], "/api/v1/images/generate", {"prompt": "a pear"})

    assert status == 500
    assert json.loads(body)["error"] == "ValueError: boom"


def test_a_server_built_without_the_api_says_so_on_both_methods():
    """`make_handler` can be built without the JSON adapter, and then the API routes
    answer with the reason instead of failing somewhere deeper."""
    handler = http_server.make_handler(cast(Any, None), cast(Any, None))
    answers = []

    class Stub(handler):  # ty: ignore[unsupported-base]
        def __init__(self):
            pass

        def _send_json(self, payload, status=200):
            answers.append((payload, status))

    Stub()._api_get("/api/v1/studio")
    Stub()._api_post("/api/v1/images/generate")

    assert answers == [({"error": "The JSON API is not configured."}, 503)] * 2


def test_the_api_video_route_needs_no_request_id(served):
    """A caller that does not want to stop the render should not have to name it."""
    body = json.loads(video_request())
    body.pop("request_id", None)

    status, _, _ = post_json(served[1], "/api/v1/videos/generate", body)

    assert status == 200
    assert served[2].jobs[-1].prompt == "A kite rises"


def test_async_operations_return_shared_results_and_client_identity(served):
    import time

    server = served[1]
    status, _, body = post_json(
        server, "/api/v1/operations", {"kind": "image", "prompt": "pear", "seed": 12, "client_id": "client"}
    )
    assert status == 202
    operation = json.loads(body)
    for _ in range(100):
        status, _, body = call(server, "/api/v1/operations/" + operation["id"])
        if json.loads(body)["status"] == "succeeded":
            break
        time.sleep(0.01)
    assert json.loads(body)["client_id"] == "client"
    status, _, body = call(server, "/api/v1/state")
    state = json.loads(body)
    assert status == 200 and state["active"] is None
    assert state["operations"][0]["id"] == operation["id"]
    result = state["operations"][0]["result_url"]
    status, _, body = call(server, result)
    assert status == 200 and json.loads(body)["images"][0]["seed"] == 12
    assert call(server, "/api/v1/operations/missing")[0] == 404
    assert call(server, "/api/v1/operations/missing/result")[0] == 404
    assert post_json(server, "/api/v1/operations/" + operation["id"] + "/cancel")[0] == 409
    assert post_json(server, "/api/v1/operations/missing/cancel")[0] == 404
    assert post_json(server, "/api/v1/operations", {"kind": "invalid"})[0] == 400


def test_async_operations_hold_the_slot_and_target_cancel(served):
    import time

    server = served[1]
    entered, released = threading.Event(), threading.Event()
    backend = served[2]
    original = backend.run

    def run(job, progress=None, cancelled=None):
        entered.set()
        released.wait(5)
        assert cancelled is not None
        if cancelled():
            raise Cancelled("stopped")
        return original(job, progress, cancelled)

    backend.run = run
    payload = {**json.loads(video_request()), "kind": "video"}
    status, _, body = post_json(server, "/api/v1/operations", payload)
    assert status == 202
    operation = json.loads(body)
    try:
        assert entered.wait(3)
        assert post_json(server, "/api/v1/operations", payload)[0] == 409
        assert post_json(server, "/api/v1/images/generate", {"prompt": "pear"})[0] == 409
        assert post_json(server, "/api/v1/images/backend", {"backend": "other"})[0] == 409
        assert post_json(server, "/api/v1/memory/release")[0] == 409
        from studio.l3_interface_adapters.api.openapi import openapi_document

        trim_example = openapi_document()["paths"]["/api/v1/audio/trim"]["post"]["requestBody"]["content"][
            "application/json"
        ]["examples"]["middle_second"]["value"]
        assert post_json(server, "/api/v1/audio/trim", trim_example)[0] == 200
        assert call(server, "/api/v1/operations/" + operation["id"] + "/result")[0] == 409
        status, _, body = call(server, "/api/v1/state")
        assert json.loads(body)["active"]["id"] == operation["id"]
        assert post_json(server, "/api/v1/operations/" + operation["id"] + "/cancel")[0] == 204
    finally:
        released.set()
    for _ in range(100):
        _, _, body = call(server, "/api/v1/operations/" + operation["id"])
        if json.loads(body)["status"] == "cancelled":
            break
        time.sleep(0.01)
    assert json.loads(body)["status"] == "cancelled"


def test_json_backend_selection_and_rewrite_state(served):
    server = served[1]
    assert post_json(server, "/api/v1/images/backend", {"backend": "other"})[0] == 204
    assert post_json(server, "/api/v1/videos/backend", {"backend": "video-other"})[0] == 204
    assert post_json(server, "/api/v1/memory/release")[0] == 204
    status, _, body = call(server, "/api/v1/rewrite/state")
    assert status == 200 and json.loads(body)["stage"] == "idle"


def test_native_ui_image_results_include_shared_operation_identity(served):
    status, _, body = call(
        served[1],
        "/generate",
        b"prompt=pear",
        **{
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Studio-Client": "tab-client",
            "X-Studio-Library": "browser-library",
        },
    )
    assert status == 200 and "data-operation-id=" in body and "data-operation-started=" in body
    assert "data-operation-completed=" in body
    _, _, state = call(served[1], "/api/v1/state")
    operation = json.loads(state)["operations"][0]
    assert operation["client_id"] == "tab-client"
    assert operation["library_id"] == "browser-library"


def test_video_results_can_be_read_from_another_client(served):
    status, _, _ = post_json(served[1], "/api/v1/videos/generate", json.loads(video_request()))
    assert status == 200
    _, _, state = call(served[1], "/api/v1/state")
    operation = json.loads(state)["operations"][0]
    status, content_type, body = call(served[1], operation["result_url"])
    assert status == 200 and content_type == "video/mp4" and body == "fake mp4 bytes"


def test_optional_api_keeps_legacy_image_and_video_routes():
    controller = SimpleNamespace(run=lambda form: "image")
    presenter = SimpleNamespace(run=lambda result: result + " markup")
    video = SimpleNamespace(run=lambda payload: VideoResult(b"mp4", 8, 8, 9, 24, None))
    handler = http_server.make_handler(cast(Any, controller), cast(Any, presenter), cast(Any, video))
    answers = []

    class Stub(handler):  # ty: ignore[unsupported-base]
        def __init__(self):
            pass

        def _read_json(self):
            return {}

        def _send_bytes(self, payload, status=200, content_type="", headers=None):
            answers.append((payload, status, content_type, headers))

    instance = Stub()
    assert instance._run_image_form({}) == "image markup"
    instance._run_video()
    assert answers == [(b"mp4", 200, "video/mp4", {})]


def test_an_async_start_returns_its_status_location(served):
    url = f"http://127.0.0.1:{served[1].server_address[1]}/api/v1/operations"
    request = urllib.request.Request(
        url, data=json.dumps({"kind": "image", "prompt": "pear"}).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=5) as answer:
        operation = json.loads(answer.read())
        assert answer.status == 202
        assert answer.headers["Location"] == operation["status_url"] == "/api/v1/operations/" + operation["id"]


def test_operation_sources_distinguish_native_and_api_requests(served):
    server = served[1]
    call(server, "/generate", b"prompt=pear", **{"Content-Type": "application/x-www-form-urlencoded"})
    call(
        server,
        "/video/generate",
        video_request(),
        **{"Content-Type": "application/json", "X-Studio-Library": "video-library"},
    )
    call(server, "/rewrite", b"prompt=pear", **{"Content-Type": "application/x-www-form-urlencoded"})
    _, _, state = call(server, "/api/v1/state")
    native = json.loads(state)["operations"]
    assert {one["kind"] for one in native} == {"image", "video", "rewrite"}
    assert all(one["source"] == "ui" for one in native)
    assert next(one for one in native if one["kind"] == "video")["library_id"] == "video-library"
    post_json(server, "/api/v1/images/generate", {"prompt": "api pear"})
    post_json(server, "/api/v1/videos/generate", json.loads(video_request()))
    post_json(server, "/api/v1/images/rewrite", {"prompt": "api pear"})
    _, _, state = call(server, "/api/v1/state")
    api_operations = json.loads(state)["operations"][:3]
    assert {one["kind"] for one in api_operations} == {"image", "video", "rewrite"}
    assert all(one["source"] == "api" for one in api_operations)


def test_native_video_timestamp_survives_immediate_result_eviction(served, monkeypatch):
    from studio.l3_interface_adapters.gateways.in_memory_operation_gateway import InMemoryOperationGateway as Operations

    retain = Operations.retain

    def retain_with_small_limit(operations, operation_id, result):
        operations._max_bytes = 1
        retain(operations, operation_id, result)

    monkeypatch.setattr(Operations, "retain", retain_with_small_limit)
    url = f"http://127.0.0.1:{served[1].server_address[1]}/video/generate"
    request = urllib.request.Request(url, data=video_request(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as answer:
        assert answer.status == 200
        assert answer.read() == b"fake mp4 bytes"
        assert float(answer.headers["X-Studio-Completed"]) > 0
    _, _, state = call(served[1], "/api/v1/state")
    assert json.loads(state)["operations"] == []


@pytest.fixture
def voice_served():
    from studio.l3_interface_adapters.gateways.audio.stub_voice_backend_gateway import StubVoiceBackendGateway

    studio = assemble_studio(
        {"fake": FakeBackendGateway()},
        {"fake": fast(StubPromptRewriter())},
        "fake",
        ("fake",),
        voice_backends={"auk": StubVoiceBackendGateway(), "auk_base": StubVoiceBackendGateway("base")},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()
    studio.shutdown()


def test_voice_capabilities_and_wav_routes(voice_served):
    status, _, body = call(voice_served, "/api/v1/voice/capabilities")
    assert status == 200 and json.loads(body)["name"] == "AuK Flash"
    assert json.loads(body)["loading"]["policy"] == "download_on_first_use"
    url = f"http://127.0.0.1:{voice_served.server_address[1]}/api/v1/voice/generate"
    request = urllib.request.Request(
        url,
        data=json.dumps({"text": "Hello", "voice": "a calm narrator"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as answer:
        assert answer.headers["Content-Type"] == "audio/wav"
        assert answer.read().startswith(b"RIFF")
        assert float(answer.headers["X-Studio-Duration"]) == 1
        operation_id = answer.headers["X-Studio-Operation"]
    with urllib.request.urlopen(
        f"http://127.0.0.1:{voice_served.server_address[1]}/api/v1/operations/{operation_id}/result"
    ) as answer:
        assert answer.read().startswith(b"RIFF")
    assert post_json(voice_served, "/api/v1/voice/generate", {"text": ""})[0] == 400


def test_batch_item_routes_return_retained_outputs(voice_served):
    import time

    status, _, body = post_json(
        voice_served,
        "/api/v1/operations",
        {
            "kind": "voice",
            "voice": "a calm narrator",
            "items": [{"text": "one"}, {"text": "two"}],
        },
    )
    operation = json.loads(body)
    assert status == 202
    for _ in range(100):
        _, _, state = call(voice_served, operation["status_url"])
        if json.loads(state)["status"] != "running":
            break
        time.sleep(0.02)
    with urllib.request.urlopen(
        f"http://127.0.0.1:{voice_served.server_address[1]}/api/v1/operations/{operation['id']}/items/1/result"
    ) as answer:
        assert answer.headers["Content-Type"] == "audio/wav"
    assert call(voice_served, f"/api/v1/operations/{operation['id']}/items/9/result")[0] == 404
    assert call(voice_served, f"/api/v1/operations/{operation['id']}/items/bad/result")[0] == 400


def test_voice_speed_template_routes_use_reference_duration_and_keep_the_instruction(voice_served):
    import time

    from tests.support.voice_audio import wav_b64

    payload = {"mode": "edit", "template": "Speed", "reference": {"wav_base64": wav_b64(seconds=3)}}
    request = urllib.request.Request(
        f"http://127.0.0.1:{voice_served.server_address[1]}/api/v1/voice/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        assert response.read().startswith(b"RIFF")
        assert float(response.headers["X-Studio-Duration"]) == 2
        operation_id = response.headers["X-Studio-Operation"]
    _, _, encoded = call(voice_served, f"/api/v1/operations/{operation_id}")
    assert json.loads(encoded)["prompt"] == "Adjust the speech speed to 1.5x."
    status, _, encoded = post_json(
        voice_served,
        "/api/v1/operations",
        {
            **payload,
            "kind": "voice",
            "items": [{"template_values": {"speed": "0.5"}}, {"template_values": {"speed": "2.0"}}],
        },
    )
    assert status == 202
    operation = json.loads(encoded)
    for _ in range(100):
        _, _, encoded = call(voice_served, operation["status_url"])
        if json.loads(encoded)["status"] != "running":
            break
        time.sleep(0.02)
    state = json.loads(encoded)
    assert state["status"] == "succeeded"
    _, _, encoded = call(voice_served, state["result_url"])
    manifest = json.loads(encoded)
    assert [item["seconds"] for item in manifest["items"]] == [6, 1.5]
    assert [item["prompt"] for item in manifest["items"]] == [
        "Adjust the speech speed to 0.5x.",
        "Adjust the speech speed to 2.0x.",
    ]
    assert manifest["items"][0]["settings"]["template"] == "Speed"


def test_readonly_backend_discovery(served):
    for workspace, backend in [("images", "fake"), ("videos", "video-fake")]:
        status, _, body = call(served[1], f"/api/v1/{workspace}/backends/{backend}")
        assert status == 200 and json.loads(body)["backend_id"] == backend
        assert call(served[1], f"/api/v1/{workspace}/backends/missing")[0] == 404
    assert call(served[1], "/api/v1/unrelated/backends/fake")[0] == 404


def test_native_voice_operation_uses_browser_identity(voice_served):
    status, _, body = call(
        voice_served,
        "/voice/operations",
        json.dumps({"kind": "voice", "text": "Hello", "voice": "a calm narrator"}).encode(),
        **{"Content-Type": "application/json", "X-Studio-Client": "voice-tab", "X-Studio-Library": "voice-library"},
    )
    assert status == 202
    operation = json.loads(body)
    assert operation["source"] == "ui"
    assert operation["client_id"] == "voice-tab"
    assert operation["library_id"] == "voice-library"


def test_api_explicit_image_backend_selects_model_before_generation(served):
    status, _, body = post_json(served[1], "/api/v1/images/generate", {"backend": "other", "prompt": "a pear"})
    assert status == 200, body
    _, _, state = call(served[1], "/api/v1/state")
    assert json.loads(state)["studio"]["image"]["active"] == "other"


def test_api_explicit_video_backend_selects_model_before_generation(served):
    payload = json.loads(video_request())
    payload["backend"] = "video-other"
    status, _, body = post_json(served[1], "/api/v1/videos/generate", payload)
    assert status == 200, body
    assert served[3].jobs


@pytest.mark.parametrize("kind,backend", [("image", "other"), ("video", "video-other")])
def test_async_batch_selects_the_requested_backend(served, kind, backend):
    import time

    item = {"prompt": "one"} if kind == "image" else json.loads(video_request())
    payload = {"kind": kind, "backend": backend, "items": [item, {**item, "prompt": "two"}]}
    status, _, body = post_json(served[1], "/api/v1/operations", payload)
    assert status == 202
    operation = json.loads(body)
    for _ in range(100):
        _, _, body = call(served[1], operation["status_url"])
        state = json.loads(body)
        if state["status"] not in ("running", "stopping"):
            break
        time.sleep(0.01)
    assert state["status"] == "succeeded", state
    _, _, body = call(served[1], state["result_url"])
    assert json.loads(body)["completed"] == 2


def test_native_image_page_still_refuses_a_stale_model(served):
    status, _, body = call(
        served[1], "/generate", b"backend=other&prompt=pear", **{"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert status == 200
    assert "The model changed in another tab." in body


def test_audio_trim_route_returns_pcm_without_reserving_an_operation(served):
    import io
    import wave

    samples = bytes(range(64))
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setparams((2, 2, 8, 16, "NONE", "not compressed"))
        stream.writeframes(samples)
    raw = output.getvalue()
    payload = {
        "audio": {"name": "selection.wav", "data": base64.b64encode(raw).decode()},
        "start_seconds": 0.25,
        "end_seconds": 1.25,
    }
    port = served[1].server_address[1]
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/audio/trim",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as answer:
        assert answer.status == 200
        assert answer.headers["Content-Type"] == "audio/wav"
        assert float(answer.headers["X-Studio-Duration"]) == 1
        with wave.open(io.BytesIO(answer.read()), "rb") as stream:
            assert stream.readframes(99) == samples[8:40]
    _, _, state = call(served[1], "/api/v1/state")
    assert json.loads(state)["active"] is None
    status, _, body = post_json(served[1], "/api/v1/audio/trim", {})
    assert status == 400 and json.loads(body)["error"]


def test_voice_models_switch_through_native_and_public_routes(voice_served):
    from studio.l3_interface_adapters.api.openapi import openapi_document

    _, _, body = call(voice_served, "/api/v1/studio")
    voice = json.loads(body)["voice"]
    assert voice["active"] == "auk"
    assert [one["name"] for one in voice["backends"]] == ["AuK Flash", "AuK"]
    status, _, body = call(voice_served, "/api/v1/voice/backends/auk_base")
    assert status == 200 and json.loads(body)["backend_id"] == "auk_base"
    assert call(voice_served, "/api/v1/voice/backends/missing")[0] == 404
    assert post_json(voice_served, "/api/v1/voice/backend", {"backend": "auk_base"})[0] == 204
    _, _, body = call(voice_served, "/api/v1/voice/capabilities")
    assert json.loads(body)["name"] == "AuK"
    port = voice_served.server_address[1]
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/voice/generate",
        data=json.dumps(
            {"mode": "design", "backend": "auk", "text": "Switch back through a run.", "voice": "A warm voice."}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        assert response.headers["Content-Type"] == "audio/wav"
    _, _, body = call(voice_served, "/api/v1/state")
    state = json.loads(body)
    assert state["studio"]["voice"]["active"] == "auk"
    assert state["operations"][0]["model"] == "AuK Flash"
    status, _, _ = call(
        voice_served, "/voice/backend", b"backend=auk_base", **{"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert status == 200
    assert "/api/v1/voice/backends/{id}" in openapi_document()["paths"]
    assert "/api/v1/voice/backend" in openapi_document()["paths"]


def test_voice_batch_records_base_backend_and_refuses_a_switch_during_work(voice_served):
    import time

    payload = {
        "kind": "voice",
        "backend": "auk_base",
        "voice": "A warm narrator.",
        "items": [{"text": "One."}, {"text": "Two."}],
    }
    status, _, body = post_json(voice_served, "/api/v1/operations", payload)
    assert status == 202
    operation = json.loads(body)
    assert operation["model"] == "AuK" and operation["backend"] == "auk_base"
    assert post_json(voice_served, "/api/v1/voice/backend", {"backend": "auk"})[0] == 409
    for _ in range(200):
        _, _, body = call(voice_served, operation["status_url"])
        state = json.loads(body)
        if state["status"] == "succeeded":
            break
        time.sleep(0.01)
    assert state["status"] == "succeeded", state
    _, _, body = call(voice_served, state["result_url"])
    assert all(item["settings"]["backend"] == "auk_base" for item in json.loads(body)["items"])
    assert post_json(voice_served, "/api/v1/voice/backend", {"backend": "auk"})[0] == 204


@pytest.mark.parametrize("backend", [[], {}, True, False, None, ""])
def test_voice_routes_reject_invalid_model_types(voice_served, backend):
    status, _, body = post_json(
        voice_served, "/api/v1/voice/generate", {"backend": backend, "text": "One.", "voice": "A warm voice."}
    )
    assert status == 400 and "model id" in json.loads(body)["error"]
    status, _, body = post_json(voice_served, "/api/v1/voice/backend", {"backend": backend})
    assert status == 400 and json.loads(body)["error"]
    status, _, body = post_json(
        voice_served,
        "/api/v1/operations",
        {"kind": "voice", "backend": backend, "voice": "A warm voice.", "items": [{"text": "One."}]},
    )
    assert status == 400 and "model id" in json.loads(body)["error"]


@pytest.mark.parametrize("backend", ["auk", "auk_base"])
def test_design_templates_discovery_single_and_batch_routes(voice_served, backend):
    import time

    _, _, encoded = call(voice_served, "/api/v1/voice/backends/" + backend)
    design = next(mode for mode in json.loads(encoded)["modes"] if mode["id"] == "design")
    assert len(design["templates"]) == 6
    payload = {"backend": backend, "mode": "design", "template": "Narration", "text": "The river flows.", "seed": 7}
    request = urllib.request.Request(
        f"http://127.0.0.1:{voice_served.server_address[1]}/api/v1/voice/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        assert response.read().startswith(b"RIFF")
        operation_id = response.headers["X-Studio-Operation"]
    _, _, encoded = call(voice_served, "/api/v1/operations/" + operation_id)
    assert json.loads(encoded)["prompt"] == "The river flows."
    status, _, encoded = post_json(
        voice_served,
        "/api/v1/operations",
        {
            **payload,
            "kind": "voice",
            "items": [{"text": "First line."}, {"text": "Second line.", "template_values": {"tone": "bright"}}],
        },
    )
    assert status == 202
    operation = json.loads(encoded)
    for _ in range(100):
        _, _, encoded = call(voice_served, operation["status_url"])
        state = json.loads(encoded)
        if state["status"] != "running":
            break
        time.sleep(0.02)
    assert state["status"] == "succeeded"
    _, _, encoded = call(voice_served, state["result_url"])
    items = json.loads(encoded)["items"]
    assert [item["prompt"] for item in items] == ["First line.", "Second line."]
    assert items[1]["settings"]["template_values"] == {"tone": "bright"}
    assert post_json(voice_served, "/api/v1/voice/generate", {**payload, "text": ""})[0] == 400


def test_native_image_batch_prepares_all_jobs_once_and_retains_browser_identity(served, monkeypatch):
    import time

    prepared = []
    monkeypatch.setattr(FakeBackendGateway, "prepare_batch", lambda self, jobs, cancelled: prepared.append(jobs))
    status, _, body = call(
        served[1],
        "/image/operations",
        json.dumps(
            {
                "kind": "image",
                "steps": 2,
                "items": [
                    {"prompt": "a pear", "seed": 7},
                    {"prompt": "an apple", "seed": 8},
                ],
            }
        ).encode(),
        **{"Content-Type": "application/json", "X-Studio-Client": "image-tab", "X-Studio-Library": "image-library"},
    )
    assert status == 202
    operation = json.loads(body)
    assert (operation["source"], operation["client_id"], operation["library_id"]) == (
        "ui",
        "image-tab",
        "image-library",
    )
    for _ in range(100):
        _, _, body = call(served[1], operation["status_url"])
        if json.loads(body)["status"] != "running":
            break
        time.sleep(0.02)
    assert json.loads(body)["status"] == "succeeded"
    assert len(prepared) == 1
    assert [(job.prompt, job.seed) for job in prepared[0]] == [("a pear", 7), ("an apple", 8)]
    _, _, body = call(served[1], json.loads(body)["result_url"])
    manifest = json.loads(body)
    assert manifest["completed"] == 2
    assert [item["prompt"] for item in manifest["items"]] == ["a pear", "an apple"]
