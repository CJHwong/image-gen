"""Check Custom Edit against a fresh stub: <port> <short-source.mp4>."""

import sys

from playwright.sync_api import expect, sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"http://127.0.0.1:{sys.argv[1]}/?workspace=video")
    expect(page.locator("#video-adapters-toggle")).to_be_hidden()
    page.locator("label[for=video-mode-edit]").click()

    def choose(label):
        page.locator("#video-adapters-toggle").click()
        page.locator("#video-adapters").get_by_role("menuitem", name=label).click()

    choose("Day to night")
    assert page.locator("#video-prompt").input_value()
    choose("Custom")
    expect(page.locator("#video-prompt")).to_have_value("")
    expect(page.locator("#video-adapter-hint")).to_contain_text("No LoRA")
    page.locator("#video-prompt").fill("Make the cup blue and keep the same scene.")
    choose("Day to night")
    choose("Custom")
    expect(page.locator("#video-prompt")).to_have_value("Make the cup blue and keep the same scene.")
    expect(page.locator("#video-generate")).to_be_disabled()
    page.locator("#video-media-upload").set_input_files(sys.argv[2])
    expect(page.locator("#video-generate")).to_be_enabled(timeout=15000)
    with page.expect_response(lambda response: response.url.endswith("/video/generate")) as response:
        page.locator("#video-generate").click()
    assert response.value.ok, response.value.text()
    payload = response.value.request.post_data_json
    assert payload["adapter"] == "custom" and payload["mode"] == "edit"
    assert payload["prompt"] == "Make the cup blue and keep the same scene."
    assert payload["clip"]["data"]
    api_payload = {**payload, "kind": "video", "request_id": "custom-api-check"}
    invalid = page.request.post(
        f"http://127.0.0.1:{sys.argv[1]}/api/v1/videos/edit",
        data={**api_payload, "adapter_strength": 0.5},
    )
    assert invalid.status == 400
    operation = page.request.post(f"http://127.0.0.1:{sys.argv[1]}/api/v1/operations", data=api_payload)
    assert operation.status == 202, operation.text()
    status_url = operation.json()["status_url"]
    page.wait_for_function("async url => (await (await fetch(url)).json()).status === 'succeeded'", arg=status_url)
    assert not errors, errors
    print("PASS Custom Edit submits without a LoRA; preset cleanup and handwritten prompts behave correctly")
    browser.close()
