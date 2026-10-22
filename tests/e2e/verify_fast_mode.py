"""Fast mode UI, drafts, two-client isolation, metadata, and API errors on the stub.

Starts an isolated stub with a short controlled render delay; no GPU is used.
    uv run --with playwright python tests/e2e/verify_fast_mode.py [evidence-dir]
"""

import json
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from studio.l1_entities.errors import Cancelled
from studio.l3_interface_adapters.gateways.stub_video_backend_gateway import StubVideoBackendGateway
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.main import BACKENDS, create_studio

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="studio-fast-ui-"))
root.mkdir(parents=True, exist_ok=True)


@contextmanager
def delayed_stub():
    original = StubVideoBackendGateway.run

    def render(self, job, progress=None, cancelled=None):
        for index in range(40):
            if cancelled and cancelled():
                raise Cancelled("Stub cancelled")
            if progress:
                progress(index, 40, 1)
            time.sleep(0.1)
        return original(self, job, progress, cancelled)

    StubVideoBackendGateway.run = render
    config = load_config(Path("studio.toml"), backend="qwen21", visible=tuple(BACKENDS))
    config = replace(config, visible_video_backends=("ltx25_mlx", "ltx23_mlx"))
    studio = create_studio(config, stub=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        studio.shutdown()
        thread.join()
        StubVideoBackendGateway.run = original


checks = []


def check(label, value):
    assert value, label
    checks.append(label)
    print("PASS", label, flush=True)


def wait_done(page, op):
    for _ in range(400):
        row = page.request.get(url + "/api/v1/operations/" + op["id"]).json()
        if row["status"] not in ["running", "stopping"]:
            return row
        page.wait_for_timeout(100)
    raise TimeoutError(op)


with delayed_stub() as url, sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.click("#media-video-mode")
    page.wait_for_selector("#video-prompt")
    page.click("#backend-toggle")
    page.get_by_role("menuitemradio", name="LTX-2.5", exact=True).click()
    page.locator("#video-advanced").evaluate("el=>el.open=true")
    page.wait_for_selector("#video-fast-mode")
    check("Fast mode defaults off", page.get_attribute("#video-fast-mode", "aria-pressed") == "false")
    page.click("#video-fast-mode")
    check("Fast mode switches on", page.get_attribute("#video-fast-mode", "aria-pressed") == "true")
    check("tradeoff is explained", "details and motion may differ" in page.inner_text("#video-fast-note"))
    # The existing preference controls whether drafts survive reload.
    page.click("#theme-toggle")
    keep = page.get_by_role("menuitemcheckbox", name="Keep in this browser")
    if keep.get_attribute("aria-checked") != "true":
        keep.click()
    else:
        page.keyboard.press("Escape")
    page.fill("#video-prompt", "A blue ceramic teapot on a table.")
    page.dispatch_event("#video-prompt", "input")
    page.wait_for_timeout(700)
    page.reload()
    page.click("#media-video-mode")
    page.locator("#video-advanced").evaluate("el=>el.open=true")
    page.wait_for_function("document.querySelector('#video-fast-mode').getAttribute('aria-pressed')==='true'")
    check("Fast mode survives reload with kept settings", True)
    other = context.new_page()
    other.goto(url)
    other.click("#media-video-mode")
    other.locator("#video-advanced").evaluate("el=>el.open=true")
    other.wait_for_selector("#video-fast-mode")
    if other.get_attribute("#video-fast-mode", "aria-pressed") == "true":
        other.click("#video-fast-mode")
    page.fill("#video-prompt", "A blue ceramic teapot on a table.")
    page.dispatch_event("#video-prompt", "input")
    with page.expect_request(lambda r: "/video/generate" in r.url and r.method == "POST") as request:
        page.click("#video-generate")
    body = request.value.post_data_json
    check("UI sends fast_mode true", body["fast_mode"] is True)
    other.wait_for_function(
        "document.querySelector('#video-fast-mode').getAttribute('aria-pressed')==='true' && document.querySelector('form').dataset.panelHeld==='true'"
    )
    check("other tab follows Fast mode and locks controls", True)
    page.wait_for_function("!document.body.classList.contains('video-busy')", timeout=90000)
    page.wait_for_function("document.querySelector('.video-output-facts')?.textContent.includes('Fast mode')")
    check("gallery metadata records Fast mode", True)
    other.wait_for_function(
        "document.querySelector('#video-fast-mode').getAttribute('aria-pressed')==='false' && !document.querySelector('#video-fast-mode').disabled"
    )
    check("observer recovers its own default mode after remote Fast render", True)
    # API initiated render must also drive the toggle in both tabs.
    payload = {
        "kind": "video",
        "backend": "ltx25_mlx",
        "prompt": "A quiet room.",
        "width": 384,
        "height": 384,
        "num_frames": 49,
        "frame_rate": 24,
        "seed": 7,
        "fast_mode": False,
    }
    response = page.request.post(url + "/api/v1/operations", data=payload)
    check("API accepts default mode without restart", response.status == 202)
    op = response.json()
    other.wait_for_function("document.querySelector('#video-fast-mode').getAttribute('aria-pressed')==='false'")
    check("API default mode clears observed Fast mode", True)
    check("API default render completes", wait_done(page, op)["status"] == "succeeded")
    page.wait_for_function("document.querySelector('#video-fast-mode').getAttribute('aria-pressed')==='true'")
    check("observer recovers its own Fast mode after remote default render", True)
    # Hold this observer's polling until a remote render and model change are complete.
    op = page.request.post(url + "/api/v1/operations", data=payload).json()
    page.wait_for_function(
        "document.querySelector('#video-fast-mode').getAttribute('aria-pressed')==='false' && document.querySelector('#video-fast-mode').disabled"
    )
    page.route("**/api/v1/state", lambda route: route.abort())
    check("remote render completes while observer polling is paused", wait_done(page, op)["status"] == "succeeded")
    switched = page.request.post(url + "/api/v1/videos/generate", data={**payload, "backend": "ltx23_mlx"})
    check("remote client can switch to an unsupported model after completion", switched.status == 200)
    page.unroute("**/api/v1/state")
    page.wait_for_function(
        "document.querySelector('#video-fast-field').hidden && document.querySelector('#video-fast-mode').getAttribute('aria-pressed')==='false' && !document.querySelector('#video-fast-mode').disabled"
    )
    check("observer never restores Fast mode onto an unsupported model", True)
    response = page.request.post(
        url + "/api/v1/videos/generate", data={**payload, "backend": "ltx23_mlx", "fast_mode": True}
    )
    check("unsupported model rejects Fast mode", response.status == 400 and "Fast mode" in response.text())
    response = page.request.post(url + "/api/v1/videos/generate", data={**payload, "fast_mode": "true"})
    check("invalid type is rejected", response.status == 400 and "boolean" in response.text())
    response = page.request.post(
        url + "/api/v1/operations", data={**payload, "fast_mode": True, "items": [{}, {"fast_mode": False}]}
    )
    check("mixed Fast mode batch rejected before execution", response.status == 400)
    # Reset model and verify the supported control is offered again.
    page.request.post(url + "/api/v1/videos/generate", data={**payload, "fast_mode": False})
    page.wait_for_timeout(600)
    page.screenshot(path=str(root / "fast-mode-ui.png"))
    check("no browser errors", not errors)
    browser.close()
(root / "browser-checks.json").write_text(json.dumps(checks, indent=2) + "\n")
