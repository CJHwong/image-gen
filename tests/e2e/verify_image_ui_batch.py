"""Prepared Image UI batches, recovery, and shared results. Use a fresh all-backends stub."""

import io
import json
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

URL = f"http://127.0.0.1:{sys.argv[1]}"


def ready(page):
    page.goto(URL)
    page.wait_for_function("Boolean(formApi) && Boolean(run)")


def inputs(page, words, steps=2, count=3):
    if page.locator("#advanced").get_attribute("open") is None:
        page.locator("#advanced summary").click()
    page.locator("#steps").fill(str(steps))
    page.locator("#prompt").fill(words)
    page.locator("#count-toggle").click()
    page.get_by_role("menuitemradio", name=f"{count} images", exact=True).click()
    page.locator("#seed").fill("7")


def idle(page):
    page.wait_for_function("!busy() && !sharedOperation", timeout=60000)


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    first = context.new_page()
    errors = []
    context.on("page", lambda page: page.on("pageerror", lambda error: errors.append(str(error))))
    first.on("pageerror", lambda error: errors.append(str(error)))
    ready(first)
    second = context.new_page()
    ready(second)
    submissions = []
    legacy = []
    first.on(
        "request",
        lambda request: (
            submissions.append(request.post_data_json)
            if request.method == "POST" and request.url.endswith("/image/operations")
            else None
        ),
    )
    first.on(
        "request",
        lambda request: (
            legacy.append(request.url) if request.method == "POST" and request.url.endswith("/generate") else None
        ),
    )
    first.locator("#templates-toggle").click()
    first.set_viewport_size({"width": 1280, "height": 500})
    first.wait_for_function(
        "document.getElementById('templates').getBoundingClientRect().bottom <= innerHeight", timeout=5000
    )
    first.keyboard.press("Escape")
    first.set_viewport_size({"width": 1280, "height": 900})
    print("PASS open template menus refit when the viewport shrinks", flush=True)

    assert first.evaluate("imageDraft().eachReference") == ""

    # Hidden edit choices must never turn Generate into an empty-reference edit.
    first.evaluate("document.getElementById('each-each').checked = true")
    inputs(first, "a pear in sunlight", steps=3)
    with first.expect_response("**/image/operations") as posted:
        first.locator("#go").click()
    operation = posted.value.json()
    assert posted.value.status == 202
    first.wait_for_function("gallery.length > 0 && Boolean(sharedOperation)")
    assert first.locator("#prompt").input_value() == ""
    first.locator("#strip .frame.arrive").first.wait_for(state="attached", timeout=10000)
    assert second.locator("#shared-operation").is_visible()
    first.reload()
    first.wait_for_function("Boolean(sharedOperation)")
    idle(first)
    idle(second)
    for page in (first, second):
        page.wait_for_function("gallery.length === 3")
        assert page.evaluate("gallery.map(entry => Number(entry.seed)).sort((a,b)=>a-b)") == [7, 8, 9]
        assert page.evaluate("new Set(gallery.map(entry => entry.id)).size") == 3
        assert page.evaluate("gallery.every(entry => entry.precision === STUDIO.backend.badge)")
        assert page.locator("#strip .pending").count() == 0
    first.wait_for_function("document.getElementById('each-all').checked")
    assert len(submissions) == 1 and not legacy
    assert [item["references"] for item in submissions[0]["items"]] == [[], [], []]
    print(
        "PASS one prepared submission, streamed items, seed sequence, reload, two-tab sync, no duplicate images",
        flush=True,
    )

    inputs(first, "exact large seeds", steps=1, count=2)
    first.locator("#seed").fill("9007199254740993")
    first.locator("#go").click()
    idle(first)
    assert [item["seed"] for item in submissions[-1]["items"]] == ["9007199254740993", "9007199254740994"]
    for page in (first, second):
        page.wait_for_function("gallery.length === 5")
        assert page.evaluate(
            "gallery.filter(entry => entry.prompt === 'exact large seeds').map(entry => entry.seed).sort()"
        ) == ["9007199254740993", "9007199254740994"]
    print("PASS exact decimal seed increments and gallery metadata above 2^53", flush=True)

    # Both cancellation controls must restore the consumed settings and reference.
    for mode in ("generate", "edit"):
        first.locator(f"label[for=mode-{mode}]").click()
        if mode == "edit":
            data = io.BytesIO()
            Image.new("RGB", (128, 128), "orange").save(data, format="PNG")
            first.locator("#reference").set_input_files(
                {"name": "orange.png", "mimeType": "image/png", "buffer": data.getvalue()}
            )
            first.wait_for_function("references.length === 1")
        for cancel in ("#go", "#shared-operation-cancel"):
            inputs(first, f"cancel {mode} via {cancel}", steps=8, count=2)
            before = first.evaluate("run.snapshotInputs()")
            first.locator("#go").click()
            first.locator("#shared-operation:not([hidden])").wait_for()
            first.wait_for_timeout(750)
            first.locator(cancel).click()
            idle(first)
            assert first.locator("#prompt").input_value() == before["prompt"]
            assert first.locator("#count").input_value() == "2"
            assert first.locator("#seed").input_value() == "7"
            assert first.evaluate("references.map(ref=>ref.b64)") == [ref["b64"] for ref in before["references"]]
    print("PASS both Cancel controls restore Generate/Edit batch inputs and reference", flush=True)

    for seed in ("abc", "1e3", "0x10", "-7"):
        inputs(first, "reject invalid batch seed", count=2)
        first.locator("#seed").fill(seed)
        count = len(submissions)
        first.locator("#go").click()
        idle(first)
        assert len(submissions) == count
        assert first.locator("#seed").input_value() == seed
        assert first.locator("#prompt").input_value() == "reject invalid batch seed"
    print("PASS invalid seeds are rejected before submission and keep the consumed inputs", flush=True)

    # Accepted operations can also fail during whole-batch validation.
    def invalid_item(route):
        payload = route.request.post_data_json
        payload["items"][1]["seed"] = "invalid"
        route.continue_(post_data=json.dumps(payload))

    first.route("**/image/operations", invalid_item)
    inputs(first, "restore after accepted failure", count=2)
    with first.expect_response("**/image/operations") as posted:
        first.locator("#go").click()
    assert posted.value.status == 202
    idle(first)
    assert first.locator("#prompt").input_value() == "restore after accepted failure"
    state = first.request.get(URL + posted.value.json()["status_url"]).json()
    assert state["status"] == "failed" and state.get("batch_completed", 0) == 0
    first.unroute("**/image/operations")
    print("PASS accepted batch validation failure restores inputs without a partial render", flush=True)

    # A reservation failure must restore the form rather than leave an empty busy page.
    first.route("**/image/operations", lambda route: route.fulfill(status=409, json={"error": "The engine is busy."}))
    inputs(first, "restore on rejection", count=2)
    first.locator("#go").click()
    idle(first)
    assert first.locator("#prompt").input_value() == "restore on rejection"
    first.unroute("**/image/operations")
    first.route("**/image/operations", lambda route: route.abort())
    first.locator("#go").click()
    idle(first)
    assert first.locator("#prompt").input_value() == "restore on rejection"
    first.unroute("**/image/operations")
    print("PASS rejected and disconnected submissions restore inputs and release controls", flush=True)
    # Composed references must remain one output after draft restoration.
    data = io.BytesIO()
    Image.new("RGB", (128, 128), "blue").save(data, format="PNG")
    first.locator("#reference").set_input_files(
        {"name": "blue.png", "mimeType": "image/png", "buffer": data.getvalue()}
    )
    first.wait_for_function("references.length === 2")
    first.locator("label[for=each-all]").click()
    first.locator("#count-toggle").click()
    first.get_by_role("menuitemradio", name="1 image", exact=True).click()
    first.locator("#prompt").fill("compose both references")
    first.locator("#prompt").dispatch_event("input")
    assert first.evaluate("imageDraft().eachReference") == ""
    first.wait_for_timeout(500)
    first.reload()
    first.wait_for_function("references.length === 2")
    assert first.evaluate("imageDraft().eachReference") == ""
    assert first.evaluate("formApi.imageCount()") == 1
    count_before = first.evaluate("gallery.length")
    first.locator("#go").click()
    idle(first)
    first.wait_for_function("gallery.some(entry => entry.prompt === 'compose both references')")
    assert first.evaluate("gallery.length") == count_before + 1
    assert first.evaluate("gallery.find(entry => entry.prompt === 'compose both references').before") is None
    first.wait_for_function("document.getElementById('each-all').checked")
    print("PASS composed references survive reload and completion without becoming per-reference batches", flush=True)
    assert not errors, errors
    browser.close()
