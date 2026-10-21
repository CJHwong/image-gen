"""Check Clear all against delayed native responses on a fresh all-backend stub."""

import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]

with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.goto(URL)
    page.wait_for_function("Boolean(kept)")

    def clear_before_delivery(route):
        response = route.fetch()
        page.evaluate("""() => {
          strip.dropAll();
          kept.forget(images => images.clear(), {kind: 'clear'});
        }""")
        route.fulfill(response=response)

    page.route("**/generate", clear_before_delivery)
    page.fill("#prompt", "an image completed before Clear all")
    page.locator("#steps").evaluate(
        "input => { input.value = input.min; input.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.locator("#go").click()
    page.wait_for_function("!document.body.classList.contains('busy')")
    assert page.evaluate("gallery.length") == 0
    print("PASS Clear all rejects a completed image whose native response arrives later", flush=True)
    page.unroute("**/generate", clear_before_delivery)

    delivered = []

    def clear_first_batch_response(route):
        response = route.fetch()
        if not delivered:
            page.evaluate("""() => {
              strip.dropAll();
              kept.forget(images => images.clear(), {kind: 'clear'});
            }""")
        delivered.append(True)
        route.fulfill(response=response)

    page.route("**/generate", clear_first_batch_response)
    page.fill("#prompt", "a batch across Clear all")
    page.locator("#steps").evaluate(
        "input => { input.value = input.min; input.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.locator("#count-toggle").click()
    page.get_by_role("menuitemradio", name="2 images", exact=True).click()
    page.locator("#go").click()
    page.wait_for_function("!document.body.classList.contains('busy')")
    assert page.evaluate("gallery.map(entry => entry.position)") == ["2 of 2"]
    page.reload()
    page.wait_for_function("gallery.length === 1")
    assert page.evaluate("gallery.map(entry => entry.position)") == ["2 of 2"]
    print("PASS a batch retains only the image completed after Clear all", flush=True)
    page.unroute("**/generate", clear_first_batch_response)

    page.goto(URL + "/?workspace=video")
    page.wait_for_function("Boolean(document.getElementById('video-studio').galleryStore)")

    def clear_video_before_delivery(route):
        response = route.fetch()
        page.evaluate("kept.clearVideos()")
        route.fulfill(response=response)

    page.route("**/video/generate", clear_video_before_delivery)
    page.fill("#video-prompt", "a clip completed before Clear all")
    page.locator("#video-generate").click()
    page.wait_for_function("videoRunState === 'idle'")
    assert page.evaluate("document.getElementById('video-studio').clips.length") == 0
    print("PASS Clear all rejects a completed video whose native response arrives later", flush=True)
    browser.close()
