"""Check external operations lock the generation form with the active workspace selected."""

import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]

with sync_playwright() as tool:
    browser = tool.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(URL)
    page.wait_for_function("Boolean(formApi)")
    page.fill("#prompt", "Keep my draft")
    page.locator("#steps").evaluate("input => input.focus()")
    old_steps = page.input_value("#steps")
    page.locator("#count-toggle").click()
    page.get_by_role("menuitemradio", name="2 images", exact=True).focus()
    operation = page.request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "image",
            "prompt": "an external operation",
            "steps": 20,
        },
    ).json()
    page.locator("#shared-operation:not([hidden])").wait_for()
    assert page.locator("#form").evaluate("element => element.inert")
    assert page.locator("#form").get_attribute("data-panel-held") == "true"
    assert page.locator("#prompt").evaluate("element => element.readOnly")
    assert page.locator("#go").is_disabled()
    assert page.locator("#backend-toggle").is_disabled()
    page.keyboard.press("Enter")
    assert page.input_value("#count") == "1"
    page.keyboard.press("ArrowUp")
    assert page.input_value("#steps") == old_steps
    page.locator("#mode-edit").evaluate("element => element.focus()")
    page.keyboard.press("Space")
    assert page.locator("#mode-generate").is_checked()
    print("PASS an external operation locks text, numeric, mode, and model controls", flush=True)
    for mode in ("image", "video", "voice"):
        assert page.locator("#media-" + mode + "-mode").is_disabled()
    assert page.evaluate("mediaMode") == "image"
    assert page.locator("#strip .frame.pending").count() == 1
    assert page.evaluate("view") == "progress"
    assert page.locator("#shared-operation-cancel").is_enabled()
    print("PASS the active workspace locks and shows its pending image", flush=True)
    page.locator("#shared-operation-cancel").click()
    page.locator("#shared-operation").wait_for(state="hidden")
    page.wait_for_function("!document.querySelector('#form').inert")
    page.locator("#media-image-mode").click()
    page.wait_for_function("mediaMode === 'image'")
    assert page.input_value("#prompt") == "Keep my draft"
    assert page.input_value("#steps") == old_steps
    assert not page.locator("#prompt").evaluate("element => element.readOnly")
    page.locator('label[for="mode-edit"]').click()
    assert page.locator("#mode-edit").is_checked()
    print("PASS cancellation unlocks controls and preserves the draft and settings", flush=True)
    page.locator('label[for="mode-generate"]').click()
    completed = page.request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "image",
            "prompt": "a short external operation",
            "steps": 2,
        },
    ).json()
    page.locator("#shared-operation:not([hidden])").wait_for()
    assert page.locator("#form").evaluate("element => element.inert")
    page.locator("#shared-operation").wait_for(state="hidden")
    page.wait_for_function("!document.querySelector('#form').inert")
    assert page.input_value("#prompt") == "Keep my draft"
    print("PASS normal completion unlocks the form without replacing the draft", flush=True)
    page.wait_for_function("gallery.length === 1")
    previous_image = page.evaluate("view")

    def delayed_result(route):
        response = route.fetch()
        page.wait_for_timeout(500)
        route.fulfill(response=response)

    page.route("**/api/v1/operations/*/result", delayed_result)
    next_image = page.request.post(
        URL + "/api/v1/operations",
        data={"kind": "image", "prompt": "the next image must appear on stage", "steps": 2},
    )
    assert next_image.status == 202
    page.wait_for_function("gallery.length === 2 && !sharedOperation")
    assert page.evaluate("view === gallery[0].id")
    assert page.evaluate("view") != previous_image
    assert not page.title().startswith("(")
    page.unroute("**/api/v1/operations/*/result", delayed_result)
    print("PASS a delayed result replaces the pending stage and clears the progress title", flush=True)
    page.locator("#steps").evaluate(
        "input => { input.value = input.min; input.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.locator("#go").click()
    page.wait_for_function("document.body.classList.contains('busy')")
    assert not page.locator("#form").evaluate("element => element.inert")
    assert page.locator("#form").get_attribute("data-panel-held") == "true"
    assert page.locator("#go").is_enabled()
    page.wait_for_function("!document.body.classList.contains('busy')")
    page.wait_for_function("!document.querySelector('#form').hasAttribute('data-panel-held')")
    print("PASS the native hold still preserves its Cancel control and releases afterward", flush=True)
    browser.close()
