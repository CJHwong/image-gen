"""Check draft completion, cancellation, marked regions, and model changes."""

import re
import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def ready(page):
    page.wait_for_function("Boolean(drafts && !drafts.loading())")
    page.wait_for_timeout(300)


def flush(page):
    page.evaluate("() => drafts.flushed()")


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(URL)
    ready(page)
    page.fill("#prompt", "A blue ceramic bowl")
    page.locator("#steps").evaluate(
        "input => { input.value = 12; input.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    page.click("#go")
    page.wait_for_function("Boolean(sharedOperation)")
    page.reload()
    ready(page)
    page.wait_for_function("gallery.length === 1 && !busy() && !sharedOperation", timeout=60000)
    page.wait_for_timeout(500)
    page.reload()
    ready(page)
    assert page.input_value("#prompt") == ""
    print("PASS Image success after reload clears the stored submitted inputs", flush=True)

    page.get_by_role("button", name="Edit this", exact=True).click()
    mark = page.get_by_label("Mark the area to change")
    mark.wait_for()
    page.get_by_role("button", name=re.compile("^Brush width")).click()
    box = mark.bounding_box()
    page.mouse.move(box["x"] + 30, box["y"] + 30)
    page.mouse.down()
    page.mouse.move(box["x"] + 80, box["y"] + 70, steps=5)
    page.mouse.up()
    page.get_by_label("What changes in the orange area?").fill("Make this part green")
    expected = page.evaluate("region.snapshot()")
    flush(page)
    page.reload()
    ready(page)
    assert page.evaluate("region.snapshot()") == expected
    assert page.get_by_label("Mark the area to change").is_visible()
    assert page.get_by_label("What changes in the orange area?").input_value() == "Make this part green"
    print("PASS Image refresh restores the marked frame, strokes, brush, and region words", flush=True)

    page.locator("#steps").evaluate(
        "input => { input.value = 20; input.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    flush(page)
    page.click("#go")
    page.wait_for_function("Boolean(sharedOperation)")
    page.reload()
    ready(page)
    operation = context.request.get(URL + "/api/v1/state").json()["active"]
    assert operation, "The marked Edit must still run during this reload check."
    response = context.request.post(URL + "/api/v1/operations/" + operation["id"] + "/cancel")
    assert response.ok, response.text()
    page.wait_for_function("!sharedOperation && !busy() && region.count() > 0", timeout=60000)
    assert page.get_by_label("What changes in the orange area?").input_value() == "Make this part green"
    print("PASS Marked Edit cancellation after reload restores strokes without another reload", flush=True)

    page.locator('label[for="mode-generate"]').click()
    page.fill("#prompt", "Keep this cancelled request")
    page.locator("#steps").evaluate(
        "input => { input.value = 20; input.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    page.click("#go")
    page.wait_for_function("Boolean(sharedOperation)")
    page.reload()
    ready(page)
    page.wait_for_function("Boolean(sharedOperation)")
    assert page.input_value("#prompt") == "Keep this cancelled request"
    assert page.locator("#media-video-mode").is_disabled()
    operation = context.request.get(URL + "/api/v1/state").json()["active"]
    response = context.request.post(URL + "/api/v1/operations/" + operation["id"] + "/cancel")
    assert response.ok, response.text()
    page.wait_for_function("!sharedOperation && !busy()", timeout=60000)
    page.reload()
    ready(page)
    assert page.input_value("#prompt") == "Keep this cancelled request"
    print("PASS Reload during generation restores inputs and locks; cancellation keeps the draft", flush=True)

    response = context.request.post(URL + "/api/v1/images/backend", data={"backend": "qwen21_turbo"})
    assert response.ok, response.text()
    page.wait_for_function("STUDIO.backend.id === 'qwen21_turbo' && !drafts.loading()")
    page.fill("#prompt", "Turbo draft")
    flush(page)
    response = context.request.post(URL + "/api/v1/images/backend", data={"backend": "qwen21"})
    assert response.ok, response.text()
    page.wait_for_function("STUDIO.backend.id === 'qwen21' && !drafts.loading()")
    assert page.input_value("#prompt") == "Keep this cancelled request"
    response = context.request.post(URL + "/api/v1/images/backend", data={"backend": "qwen21_turbo"})
    assert response.ok, response.text()
    page.wait_for_function("STUDIO.backend.id === 'qwen21_turbo' && !drafts.loading()")
    assert page.input_value("#prompt") == "Turbo draft"
    print("PASS Model switches retain separate browser drafts", flush=True)

    other = context.new_page()
    idle = context.request.get(URL + "/api/v1/state").json()
    other.route("**/api/v1/state", lambda route: route.fulfill(json=idle))
    other.goto(URL)
    ready(other)
    page.fill("#prompt", "An earlier submission")
    page.click("#go")
    page.wait_for_function("Boolean(sharedOperation)")
    other.fill("#prompt", "A newer draft from the second tab")
    flush(other)
    page.wait_for_function("!busy() && !sharedOperation", timeout=60000)
    page.wait_for_timeout(500)
    page.reload()
    ready(page)
    assert page.input_value("#prompt") == "A newer draft from the second tab"
    other.close()
    print("PASS A completion cannot remove a newer draft from another tab", flush=True)

    response = context.request.post(
        URL + "/api/v1/operations",
        data={"kind": "image", "prompt": "An external API request", "size": "512x512"},
    )
    assert response.status == 202, response.text()
    page.wait_for_function(
        """async id => {
      const operation = await (await fetch('/api/v1/operations/' + id)).json();
      if (operation.status === 'failed') throw new Error(operation.error);
      return operation.status === 'succeeded';
    }""",
        arg=response.json()["id"],
        timeout=60000,
    )
    page.wait_for_function("!sharedOperation", timeout=60000)
    page.reload()
    ready(page)
    assert page.input_value("#prompt") == "A newer draft from the second tab"
    print("PASS An external API completion keeps the human draft", flush=True)

    page.locator("#media-video-mode").click()
    page.wait_for_function("mediaMode === 'video' && !workspaceSwitchPending")
    page.fill("#video-prompt", "A quiet lake under the moon")
    page.locator("#video-advanced summary").click()
    page.fill("#video-seed", "41")
    page.click("#video-generate")
    page.wait_for_function(
        "videoRunState === 'idle' && !sharedOperation && videoStudio.clips.length > 0", timeout=60000
    )
    page.wait_for_timeout(500)
    page.reload()
    ready(page)
    assert page.input_value("#video-prompt") == ""
    assert page.input_value("#video-seed") == "41"
    print("PASS Video completion clears words and keeps its saved settings", flush=True)

    page.evaluate("setKeep(false)")
    flush(page)
    page.reload()
    ready(page)
    assert page.input_value("#prompt") == ""
    assert page.evaluate("keeping") is False
    print("PASS Keep off removes drafts and prevents restoration", flush=True)
    assert not errors, errors
    browser.close()
