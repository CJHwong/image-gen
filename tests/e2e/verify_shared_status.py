"""One status bar and monotonic batch-edit progress. Run against a fresh all-backends stub."""

import io
import sys
import time
import uuid
from functools import partial
from itertools import pairwise

from PIL import Image
from playwright.sync_api import sync_playwright

URL = f"http://127.0.0.1:{sys.argv[1]}"
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 850})
    page.goto(URL)
    page.wait_for_function("typeof formApi !== 'undefined' && Boolean(formApi)")
    assert page.locator(".topbar .status, #status, #status-text").count() == 0
    assert page.locator("#shared-operation").is_hidden()
    draft_ids = set()
    # Restoration belongs to the submission, independently of browser persistence.
    for keeping in ("on", "off"):
        for mode in ("generate", "edit"):
            page.close()
            page = browser.new_page(viewport={"width": 1280, "height": 850})
            page.add_init_script(f"localStorage.setItem('studio-keep', '{keeping}')")
            page.goto(URL)
            page.wait_for_function("typeof formApi !== 'undefined' && Boolean(formApi)")
            page.locator(f"label[for=mode-{mode}]").click()
            if mode == "edit":
                data = io.BytesIO()
                Image.new("RGB", (128, 128), "orange").save(data, format="PNG")
                page.locator("#reference").set_input_files(
                    {"name": "cancel-reference.png", "mimeType": "image/png", "buffer": data.getvalue()}
                )
                page.wait_for_function("references.length === 1")
            for cancel in ("#go", "#shared-operation-cancel"):
                if page.locator("#advanced").get_attribute("open") is None:
                    page.locator("#advanced summary").click()
                page.locator("#steps").fill("8")
                prompt = f"restore {mode} {keeping} inputs after {cancel}"
                page.locator("#prompt").fill(prompt)
                before = page.evaluate("references.map(ref => ref.b64)")
                page.locator("#go").click()
                page.locator("#shared-operation:not([hidden])").wait_for()
                page.wait_for_timeout(750)
                draft_id = page.evaluate("sharedOperation.settings.draft_id")
                assert uuid.UUID(draft_id).version == 4
                assert draft_id not in draft_ids
                draft_ids.add(draft_id)
                assert page.evaluate("run.prepareCancel({...sharedOperation, settings: {draft_id: 'stale'}})") is False
                # Footer Cancel must preserve an already armed snapshot. Shared-bar
                # cases stay unprepared, proving the button itself arms restoration.
                if cancel == "#go":
                    assert page.evaluate("run.prepareCancel(sharedOperation)") is True
                    assert page.evaluate("run.prepareCancel(sharedOperation)") is True
                page.locator(cancel).click()
                page.wait_for_function("!document.body.classList.contains('busy')", timeout=30000)
                assert page.locator("#prompt").input_value() == prompt
                assert page.evaluate("references.map(ref => ref.b64)") == before
                page.locator("#shared-operation").wait_for(state="hidden")
    print(
        "PASS both Cancel doors restore Generate/Edit inputs with Keep on/off, repeated clicks, stale-draft protection",
        flush=True,
    )
    page.close()
    page = browser.new_page(viewport={"width": 1280, "height": 850})
    page.goto(URL)
    page.wait_for_function("typeof formApi !== 'undefined' && Boolean(formApi)")
    page.locator("label[for=mode-edit]").click()
    for index, color in enumerate(("red", "blue"), 1):
        data = io.BytesIO()
        Image.new("RGB", (128, 128), color).save(data, format="PNG")
        page.locator("#reference").set_input_files(
            {"name": color + ".png", "mimeType": "image/png", "buffer": data.getvalue()}
        )
        page.wait_for_function("count => references.length === count", arg=index)
    page.locator("label[for=each-each]").click()
    page.locator("#advanced summary").click()
    page.locator("#steps").fill("8")
    page.locator("#prompt").fill("make the background green")
    page.evaluate("""() => {
      window.statusSamples = [];
      window.statusTimer = setInterval(() => {
        const panel = document.getElementById('shared-operation');
        if (panel.hidden) return;
        const progress = document.getElementById('shared-operation-progress');
        const text = document.querySelector('#canvas .percent')?.textContent;
        statusSamples.push({id: panel.dataset.operationId, bar: progress.hasAttribute('value') ? progress.value : null,
          preview: text?.endsWith('%') ? parseInt(text) : null});
      }, 25);
    }""")
    page.locator("#go").click()
    page.locator("#shared-operation:not([hidden])").wait_for()
    page.screenshot(path="/tmp/studio-status-desktop.png")
    page.set_viewport_size({"width": 390, "height": 844})
    box = page.locator("#shared-operation-cancel").bounding_box()
    assert box and 0 <= box["y"] < 844 - box["height"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path="/tmp/studio-status-mobile.png")
    deadline = time.monotonic() + 90
    while page.locator("#shared-operation").is_visible() and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    assert page.locator("#shared-operation").is_hidden()
    samples = page.evaluate("clearInterval(statusTimer); statusSamples")
    for source in ("bar", "preview"):
        values = [s[source] for s in samples if s[source] is not None]
        assert len(set(values)) > 3, (source, values)
        assert all(a <= b for a, b in pairwise(values)), (source, values)
        assert max(values) < 100
    assert page.locator("#strip .frame:not(.pending)").count() == 2
    print(
        "PASS one status bar, batch-edit progress never decreases, no premature 100%, mobile cancel, completion",
        flush=True,
    )
    # Hold representative server snapshots to inspect each mobile workspace,
    # including Voice's indeterminate phase, without loading a model.
    page.emulate_media(reduced_motion="reduce")
    assert page.locator(".operation-indicator").evaluate("node => getComputedStyle(node).animationName") == "none"
    state = page.request.get(URL + "/api/v1/state").json()
    for kind in ("video", "voice"):
        active = {
            "id": "layout-" + kind,
            "kind": kind,
            "workspace": kind,
            "status": "running",
            "mode": "generate",
            "model": "A long model name for layout",
            "started_at": time.time(),
            "settings": {},
            "progress": {"stage": "preparing", "step": 0, "total": 0},
        }

        def snapshot(route, *, active):
            route.fulfill(json={**state, "active": active})

        page.route("**/api/v1/state", partial(snapshot, active=active))
        page.wait_for_function("mode => mediaMode === mode", arg=kind)
        box = page.locator("#shared-operation-cancel").bounding_box()
        assert box and 0 <= box["y"] < 844 - box["height"], (kind, box)
        assert not page.locator("#shared-operation-progress").get_attribute("value")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.unroute("**/api/v1/state")
        page.wait_for_function("!document.body.classList.contains('busy')")
    print(
        "PASS Video and Voice status/cancel remain in the mobile viewport; unknown progress stays indeterminate",
        flush=True,
    )
    active = {**active, "id": "stopping-rewrite", "kind": "rewrite", "workspace": "video", "status": "stopping"}
    page.route("**/api/v1/state", partial(snapshot, active=active))
    page.wait_for_function("document.getElementById('shared-operation-label').textContent === 'Stopping'")
    assert page.locator("#shared-operation-cancel").is_disabled()
    assert "Stopping" in page.locator("#shared-operation-cancel").inner_text()
    print("PASS cancellation during rewrite preparation consistently shows Stopping", flush=True)
    browser.close()
