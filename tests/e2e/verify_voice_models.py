"""Check Voice model discovery, selection, request identity, and clip provenance."""

import sys

from playwright.sync_api import sync_playwright
from voice_helpers import choose_voice_profile

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("document.getElementById('voice-studio').capabilities.backend_id === 'drama3'")
    check("Voice starts with Drama-3", page.locator("#backend-toggle .name").inner_text().strip() == "Drama-3")
    page.locator("#backend-toggle").click()
    page.get_by_role("menuitemradio", name="AuK Flash", exact=True).click()
    page.wait_for_function("document.getElementById('voice-studio').capabilities.backend_id === 'auk'")
    choose_voice_profile(page)
    check("AuK Flash remains selectable", "AuK Flash" in page.locator("#backend-toggle").inner_text())
    capabilities = context.request.get(URL + "/api/v1/voice/backends/auk_base")
    check(
        "the API describes AuK without a model switch",
        capabilities.status == 200
        and page.evaluate("document.getElementById('voice-studio').capabilities.backend_id") == "auk",
    )
    page.locator("#voice-text").fill("This clip belongs to AuK Flash.")
    page.locator("#voice-generate").click()
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 1 && !document.getElementById('voice-studio').locked"
    )
    page.locator("#backend-toggle").click()
    page.get_by_role("menuitemradio", name="AuK", exact=True).click()
    page.wait_for_function("document.getElementById('voice-studio').capabilities.backend_id === 'auk_base'")
    check("the shared picker selects AuK", "AuK Flash" not in page.locator("#backend-toggle").inner_text())
    check(
        "a model switch keeps the original clip model",
        "AuK Flash" in page.locator("#voice-output-details").inner_text(),
    )
    choose_voice_profile(page)
    page.locator("#voice-text").fill("This new clip belongs to AuK.")
    with page.expect_request(
        lambda request: request.method == "POST" and request.url.endswith("/voice/operations")
    ) as request:
        page.locator("#voice-generate").click()
    payload = request.value.post_data_json
    check("the selected model reaches the native request", payload["backend"] == "auk_base")
    check("AuK does not reuse a Flash voice design", payload["mode"] == "design" and "reference" not in payload)
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 2 && !document.getElementById('voice-studio').locked"
    )
    check("both model results remain in the gallery", page.locator(".voice-clip[data-take-id]").count() == 2)
    check(
        "the new clip reports its actual model", "AuK Flash" not in page.locator("#voice-output-details").inner_text()
    )
    response = context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk"})
    check("the API accepts a Voice model switch", response.status in [200, 204])
    page.wait_for_function("document.getElementById('voice-studio').capabilities.backend_id === 'auk'")
    check("an API model switch reaches the shared picker", "AuK Flash" in page.locator("#backend-toggle").inner_text())
    check(
        "the current sidebar cannot change the AuK clip provenance",
        "AuK Flash" not in page.locator("#voice-output-details").inner_text(),
    )
    choose_voice_profile(page)
    page.locator("#voice-text").fill("This Flash recording keeps its requested Design mode.")
    with page.expect_request(
        lambda request: request.method == "POST" and request.url.endswith("/voice/operations")
    ) as request:
        page.locator("#voice-generate").click()
    payload = request.value.post_data_json
    check(
        "Flash Design does not use a finished script as a reference",
        payload["backend"] == "auk" and payload["mode"] == "design" and "reference" not in payload,
    )
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 3")
    check("the browser reports no page errors", not errors)
    browser.close()
