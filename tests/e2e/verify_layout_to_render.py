"""Check Layout to Render against a fresh stub: <port> <layout.mp4> <look.png>."""

import sys

from playwright.sync_api import expect, sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    base = f"http://127.0.0.1:{sys.argv[1]}"
    page.goto(base + "/?workspace=video")
    page.locator("label[for=video-mode-edit]").click()
    page.locator("#video-adapters-toggle").click()
    page.locator("#video-adapters").get_by_role("menuitem", name="Layout to Render").click()
    page.locator("#video-prompt").fill("A stone well in summer sunlight, rough stone and golden grass.")
    expect(page.locator("#video-generate")).to_be_disabled()
    page.locator("#video-media-upload").set_input_files(sys.argv[2])
    expect(page.locator("#video-go-sub")).to_contain_text("look image", timeout=15000)
    page.locator("#video-media-upload").set_input_files(sys.argv[3])
    expect(page.locator("#video-reference-tray")).to_be_visible()
    expect(page.locator("#video-reference-tray strong")).to_have_text("Look image")
    expect(page.locator("#video-generate")).to_be_enabled(timeout=15000)
    page.reload()
    expect(page.locator("#video-adapter-name")).to_have_text("Layout to Render")
    expect(page.locator("#video-generate")).to_be_enabled(timeout=15000)
    with page.expect_response(lambda response: response.url.endswith("/video/generate")) as response:
        page.locator("#video-generate").click()
    assert response.value.ok, response.value.text()
    payload = response.value.request.post_data_json
    assert payload["adapter"] == "layout-to-render" and payload["mode"] == "edit"
    assert payload["clip"]["data"] and len(payload["references"]) == 1
    assert payload["references"][0]["frame_index"] == 0
    invalid = page.request.post(base + "/api/v1/videos/edit", data={**payload, "references": []})
    assert invalid.status == 400 and "needs between 1 and 1" in invalid.text()
    operation = page.request.post(base + "/api/v1/operations", data={**payload, "kind": "video"})
    assert operation.status == 202, operation.text()
    page.wait_for_function(
        "async url => (await (await fetch(url)).json()).status === 'succeeded'", arg=operation.json()["status_url"]
    )
    page.locator("#video-adapters-toggle").click()
    page.locator("#video-adapters").get_by_role("menuitem", name="Custom", exact=False).click()
    expect(page.locator("#video-reference-tray")).to_be_hidden()
    assert not errors, errors
    print("PASS Layout UI requires look image, restores draft, submits both inputs, and shares API validation")
    browser.close()
