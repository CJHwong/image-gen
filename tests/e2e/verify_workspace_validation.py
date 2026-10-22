"""Inactive Voice constraints must not block native Image form submission.

Run against a fresh stub: uv run --with playwright python tests/e2e/verify_workspace_validation.py <port>
"""

import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(URL + "/?workspace=voice")
    page.locator("details.voice-advanced").evaluate("(el) => el.open = true")
    limit = page.locator("#voice-param-max_tokens")
    limit.fill("4096")
    page.locator("#voice-text").fill("A short recording.")
    assert page.locator("#voice-generate").is_disabled()
    assert "2048" in page.locator("#voice-go-sub").inner_text()
    print("PASS Voice explains its supported token range before submission", flush=True)
    page.locator("#media-image-mode").click()
    page.locator("#prompt").fill("A red cup on a table.")
    assert page.locator("#form").evaluate("(form) => form.checkValidity()")
    with page.expect_request(lambda request: request.method == "POST" and request.url.endswith("/generate")):
        page.locator("#go").click()
    page.wait_for_function(
        '!document.body.classList.contains("busy") && document.querySelectorAll("#strip .frame:not(.pending)").length === 1'
    )
    page.wait_for_timeout(1500)
    print("PASS hidden Voice values do not block Image Generate", flush=True)
    page.get_by_role("button", name="Edit this", exact=True).click()
    page.wait_for_function(
        'document.querySelector("#mode-edit").checked && document.querySelectorAll("#thumbs .thumb").length === 1'
    )
    page.locator("#prompt").fill("Make the cup blue.")
    with page.expect_request(lambda request: request.method == "POST" and request.url.endswith("/generate")):
        page.locator("#go").click()
    page.wait_for_function(
        '!document.body.classList.contains("busy") && document.querySelectorAll("#strip .frame:not(.pending)").length === 2'
    )
    print("PASS hidden Voice values do not block Image Edit", flush=True)
    page.locator("#media-voice-mode").click()
    limit.fill("2048")
    assert page.locator("#voice-generate").is_enabled()
    print("PASS correcting the token limit enables Voice generation", flush=True)
    browser.close()
