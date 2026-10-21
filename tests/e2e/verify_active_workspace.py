"""Check shared operation snapshots select and lock every media workspace.

The stub finishes video immediately. Hold deterministic server snapshots to check
reloads, stopping, and terminal states without a model or timing races.
"""

import sys
import time

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]

with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    snapshot = context.request.get(URL + "/api/v1/state").json()
    snapshot["active"] = None
    snapshot["operations"] = []
    context.route("**/api/v1/state", lambda route: route.fulfill(json=snapshot))
    tabs = [context.new_page(), context.new_page()]
    errors = []
    for tab in tabs:
        tab.on("pageerror", lambda error: errors.append(str(error)))
        tab.goto(URL)
        tab.wait_for_function("Boolean(formApi)")
        tab.fill("#prompt", "Keep this image draft")
        tab.locator("#size").select_option("768x512", force=True)
        tab.locator("#steps").evaluate(
            "input => { input.value = 17; input.dispatchEvent(new Event('input', {bubbles: true})); }"
        )
    for kind, mode in (("image", "edit"), ("image", "generate"), ("video", "edit"), ("voice", "clone")):
        tabs[0].evaluate("setMediaMode('voice' === mediaMode ? 'image' : 'voice')")
        operation = {
            "id": "shared-preview-" + kind + "-" + mode,
            "kind": kind,
            "workspace": kind,
            "mode": mode,
            "status": "running",
            "source": "api",
            "client_id": "external",
            "started_at": time.time(),
            "model": "Test model",
            "width": 768,
            "height": 512,
            "settings": {},
            "progress": {"running": True, "stage": "running", "step": 2, "total": 8},
        }
        snapshot["active"] = operation
        try:
            for tab in tabs:
                tab.wait_for_function("expected => sharedOperation?.id === expected", arg=operation["id"])
                assert tab.evaluate("mediaMode") == kind
                for workspace in ("image", "video", "voice"):
                    assert tab.locator("#media-" + workspace + "-mode").is_disabled()
            tabs[1].reload()
            tabs[1].wait_for_function("expected => sharedOperation?.id === expected", arg=operation["id"])
            assert tabs[1].evaluate("mediaMode") == kind
            for tab in tabs:
                if kind == "image":
                    assert tab.locator("#strip .frame.pending").count() == 1
                    assert tab.evaluate("view") == "progress"
                    assert tab.locator("#mode-" + mode).is_checked()
                    assert tab.locator('[data-param="strength"]').evaluate("element => element.hidden") == (
                        mode == "edit"
                    )
                    assert tab.locator('[data-param="resolution"]').evaluate("element => element.hidden") == (
                        mode == "generate"
                    )
                elif kind == "video":
                    assert tab.evaluate(
                        "Boolean(videoStudio.generationProgress && videoStudio.pendingRender && videoStudio.showRender)"
                    )
                    assert tab.evaluate("videoMode") == mode
                else:
                    assert tab.evaluate("Boolean(voiceStudio.activeOperation && voiceStudio.showGeneration)")
                    assert tab.evaluate("voiceStudio.mode") == mode
            print(
                "PASS "
                + kind
                + " selects its workspace and mode, locks controls, and restores its preview after reload",
                flush=True,
            )
            operation["status"] = "stopping"
            operation["progress"]["stopping"] = True
            for tab in tabs:
                tab.wait_for_function("sharedOperation?.status === 'stopping'")
                assert tab.locator("#media-image-mode").is_disabled()
        finally:
            snapshot["active"] = None
        for tab in tabs:
            tab.wait_for_function("!sharedOperation")
            assert tab.locator("#media-image-mode").is_enabled()
            if tab is tabs[0]:
                assert tab.input_value("#prompt") == "Keep this image draft"
                assert tab.input_value("#size") == "768x512"
                assert tab.input_value("#steps") == "17"
            assert tab.locator("#strip .frame.pending").count() == 0
            assert not tab.evaluate("Boolean(videoStudio.generationProgress)")
            assert not tab.title().startswith("(")
        print("PASS " + kind + " termination clears pending state and preserves drafts", flush=True)
    assert not errors, errors
    browser.close()
