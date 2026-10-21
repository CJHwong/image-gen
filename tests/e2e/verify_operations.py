"""Drive the JSON API while three tabs follow the same server.

Run against a fresh `uv run studio --stub --all-backends --port <port>`.
"""

import sys
import time

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def completed(request, operation_id):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        state = request.get(URL + "/api/v1/operations/" + operation_id).json()
        if state["status"] not in ("running", "stopping"):
            return state
        time.sleep(0.1)
    raise AssertionError("The operation did not finish.")


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


def active_at(request, label):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        operation = request.get(URL + "/api/v1/state").json()["active"]
        if operation and operation.get("progress", {}).get("label") == label:
            return operation
        time.sleep(0.1)
    raise AssertionError("The operation did not reach " + label)


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    errors = []
    tabs = [context.new_page(), context.new_page()]
    for tab in tabs:
        tab.on("pageerror", lambda error: errors.append(str(error)))
        tab.on("dialog", lambda dialog: dialog.accept())
        tab.goto(URL)
        tab.locator("#go").wait_for()
    tabs[1].fill("#prompt", "Keep this unfinished draft")
    request = context.request
    result = request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "image",
            "prompt": "a red pear",
            "seed": 7,
            "size": "512x512",
        },
    )
    check("an asynchronous request returns an operation", result.status == 202)
    operation_id = result.json()["id"]
    for tab in tabs:
        tab.locator('#shared-operation[data-operation-id="' + operation_id + '"]:not([hidden])').wait_for()
    check("both tabs disable a conflicting run", all(tab.locator("#go").is_disabled() for tab in tabs))
    refusal = request.post(URL + "/api/v1/images/generate", data={"prompt": "a conflicting run"})
    check("a conflicting API request returns 409", refusal.status == 409)
    third = context.new_page()
    third.on("pageerror", lambda error: errors.append(str(error)))
    third.on("dialog", lambda dialog: dialog.accept())
    third.goto(URL)
    third.locator('#shared-operation[data-operation-id="' + operation_id + '"]:not([hidden])').wait_for()
    tabs.append(third)
    check("a new tab adopts the active operation", True)
    check("the API image finishes", completed(request, operation_id)["status"] == "succeeded")
    for tab in tabs:
        tab.wait_for_function('document.querySelectorAll("#strip .frame").length === 1')
    check("every tab imports the completed image once", True)
    check("the observer keeps its unfinished draft", tabs[1].input_value("#prompt") == "Keep this unfinished draft")
    tabs[1].reload()
    tabs[1].wait_for_function('document.querySelectorAll("#strip .frame").length === 1')
    check("reload retains one image without duplication", True)
    result = request.post(
        URL + "/api/v1/operations", data={"kind": "image", "prompt": "cancel this image", "size": "512x512"}
    )
    cancel_id = result.json()["id"]
    third.locator('#shared-operation[data-operation-id="' + cancel_id + '"]:not([hidden])').wait_for()
    third.locator("#shared-operation-cancel").click()
    check("another tab cancels the matching operation", completed(request, cancel_id)["status"] == "cancelled")
    stale = request.post(URL + "/api/v1/operations/" + operation_id + "/cancel")
    check("a stale cancel cannot stop another run", stale.status == 409)
    video = request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "video",
            "prompt": "a slow camera move",
            "width": 384,
            "height": 384,
            "num_frames": 9,
            "frame_rate": 24,
            "seed": 7,
        },
    ).json()
    check("a brief video operation finishes", completed(request, video["id"])["status"] == "succeeded")
    for tab in tabs:
        tab.wait_for_function(
            "document.getElementById('video-studio').clips.some(clip => clip.metadata?.operationId === '"
            + video["id"]
            + "')"
        )
    check("tabs find a result completed between polls", True)

    for tab in tabs:
        tab.locator("#media-image-mode").click()
        tab.wait_for_function("mediaMode === 'image' && !workspaceSwitchPending")
    owner = tabs[0]
    owner.fill("#prompt", "a UI image that survives its originating tab reload")
    owner.locator("#go").click()
    owner.locator("#shared-operation:not([hidden])").wait_for()
    ui_operation = request.get(URL + "/api/v1/state").json()["active"]
    check("a UI image appears in the shared API state", ui_operation["kind"] == "image")
    previous_client = owner.evaluate("CLIENT_ID")
    owner.reload()
    check("reload creates a new operation owner identity", owner.evaluate("CLIENT_ID") != previous_client)
    check(
        "the UI operation continues after its originating tab reloads",
        completed(request, ui_operation["id"])["status"] == "succeeded",
    )
    for tab in tabs:
        tab.wait_for_function('document.querySelectorAll("#strip .frame").length === 2')
    check("the reloaded owner and every observer recover one result", True)

    owner.fill("#prompt", "a UI image that reaches every tab once")
    owner.locator("#go").click()
    owner.wait_for_function('!document.body.classList.contains("busy")')
    for tab in tabs:
        tab.wait_for_function('document.querySelectorAll("#strip .frame").length === 3')
    check("native UI output and shared polling do not duplicate the image", True)

    owner.fill("#prompt", "two native batch images")
    owner.locator("#count-toggle").click()
    owner.get_by_role("menuitemradio", name="2 images", exact=True).click()
    owner.locator("#go").click()
    batch_operation = active_at(request, "2 of 2")
    previous_client = owner.evaluate("CLIENT_ID")
    owner.reload()
    check("reload during the batch creates a new owner identity", owner.evaluate("CLIENT_ID") != previous_client)
    check(
        "a native batch stays one operation through its second image",
        completed(request, batch_operation["id"])["status"] == "succeeded",
    )
    batch_result = request.get(URL + "/api/v1/operations/" + batch_operation["id"] + "/result").json()
    check("the native batch retains both image results", len(batch_result["images"]) == 2)
    for tab in tabs:
        tab.wait_for_function('document.querySelectorAll("#strip .frame").length === 5')
    check("reload during a native batch recovers both images without duplicates", True)

    partial = request.post(
        URL + "/api/v1/operations",
        data={"kind": "image", "prompt": "retain the first batch image", "count": 2},
    ).json()
    active_at(request, "2 of 2")
    request.post(URL + "/api/v1/operations/" + partial["id"] + "/cancel")
    check("an API batch can stop after its first result", completed(request, partial["id"])["status"] == "cancelled")
    retained = request.get(URL + "/api/v1/operations/" + partial["id"] + "/result").json()
    check("a cancelled batch retains its finished image", len(retained["images"]) == 1)
    for tab in tabs:
        tab.wait_for_function('document.querySelectorAll("#strip .frame").length === 6')
    check("every observer imports the partial batch result", True)

    tabs[1].fill("#prompt", "Keep this rewrite draft")
    rewrite = request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "rewrite",
            "workspace": "image",
            "prompt": "a candle in a window",
        },
    ).json()
    check("the API rewrite finishes", completed(request, rewrite["id"])["status"] == "succeeded")
    for tab in tabs:
        tab.locator("#shared-rewrite-result:not([hidden])").wait_for()
        check("the rewrite result reaches an observer", "A longer version" in tab.input_value("#shared-rewrite-text"))
    check(
        "a completed rewrite preserves an unfinished draft", tabs[1].input_value("#prompt") == "Keep this rewrite draft"
    )
    tabs[1].locator("#shared-rewrite-use").click()
    check("Use prompt explicitly applies the rewrite result", "A longer version" in tabs[1].input_value("#prompt"))

    tabs[1].fill("#prompt", "Keep this model-switch draft")
    switched = request.post(URL + "/api/v1/images/backend", data={"backend": "qwen21"})
    check("the API selects an image model", switched.status in (200, 204))
    for tab in tabs:
        tab.wait_for_function("document.querySelector('[name=backend]').value === 'qwen21'")
    check(
        "model selection reaches every tab without losing drafts",
        tabs[1].input_value("#prompt") == "Keep this model-switch draft",
    )
    for tab in tabs:
        tab.fill("#prompt", "A valid draft after the failed operation")
    failure = request.post(URL + "/api/v1/operations", data={"kind": "image", "prompt": ""}).json()
    failed = completed(request, failure["id"])
    check("a failed operation retains its error", failed["status"] == "failed" and bool(failed["error"]))
    for tab in tabs:
        tab.locator("#shared-operation").wait_for(state="hidden")
        tab.wait_for_function('!document.querySelector("#go").disabled')
    check("failure clears active status and releases the run controls", True)
    check("the browser reports no page errors", not errors)
    browser.close()
