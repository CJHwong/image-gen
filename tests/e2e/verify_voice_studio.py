"""Check Voice controls, continuous clips, storage, and workspace isolation.

Run against a fresh `uv run studio --stub --all-backends --port <port>`.
"""

import sys

from playwright.sync_api import sync_playwright
from voice_helpers import choose_voice_profile, create_voice_clips, generate_another_take, open_clip_actions

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
    page.on("dialog", lambda dialog: dialog.accept())
    page.route(
        "**/api/v1/state", lambda route: route.fulfill(status=503, json={"error": "Status is temporarily unavailable."})
    )
    context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.locator("#voice-text").fill("This draft waits for the shared server state.")
    check("Voice waits for capabilities before generation", page.locator("#voice-generate").is_disabled())
    page.unroute("**/api/v1/state")
    page.wait_for_function("document.getElementById('voice-studio').capabilities.modes.length === 3")
    choose_voice_profile(page)
    page.locator("#voice-text").fill("")
    page.get_by_role("button", name="Voice", exact=True).click()
    page.wait_for_function("document.getElementById('media-voice-mode').getAttribute('aria-pressed') === 'true'")
    check("Voice has its own workspace", page.locator("#media-voice-mode").get_attribute("aria-pressed") == "true")
    check("Voice offers only AuK", "AuK" in page.locator("#backend-toggle").inner_text())
    check("an empty script cannot run", page.locator("#voice-generate").is_disabled())
    page.locator("#voice-text").fill("Hello from the voice studio. This is the second sentence.")
    page.locator("#voice-description").fill(
        "A woman in her thirties, calm, warm and clear, with a neutral American accent and a steady pace."
    )
    check(
        "the complete script stays in one segment",
        page.evaluate("document.getElementById('voice-studio').segments.length") == 1,
    )
    page.evaluate("""() => {
      const original = AudioContext.prototype.decodeAudioData;
      window.voiceDecodeCalls = 0;
      AudioContext.prototype.decodeAudioData = function(...args) {
        window.voiceDecodeCalls++;
        return original.apply(this, args);
      };
    }""")
    page.locator("#voice-generate").click()
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 1", timeout=120000)
    check("one press generates one continuous clip", page.locator(".voice-clip[data-take-id]").count() == 1)
    check("the clip needs only one audio decode", page.evaluate("window.voiceDecodeCalls") == 1)
    create_voice_clips(page, ["An independent second recording."])
    open_clip_actions(page)
    check(
        "the clip menu does not join independent recordings",
        page.get_by_role("menuitem", name="Play joined audio", exact=True).count() == 0,
    )
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Select audio 1", exact=True).click()
    generate_another_take(page)
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 3", timeout=120000)
    check(
        "reuse preserves every previous recording",
        page.locator(".voice-clip[data-take-id]").count() == 3,
    )
    page.get_by_role("button", name="Image", exact=True).click()
    page.wait_for_function("document.getElementById('media-image-mode').getAttribute('aria-pressed') === 'true'")
    check("Image remains separate", page.locator("#image-controls").is_visible())
    page.get_by_role("button", name="Voice", exact=True).click()
    page.wait_for_function("document.getElementById('media-voice-mode').getAttribute('aria-pressed') === 'true'")
    check("workspace switches preserve takes", page.locator(".voice-clip[data-take-id]").count() == 3)
    page.reload()
    page.get_by_role("button", name="Voice", exact=True).click()
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 3")
    check(
        "reload preserves the cleared form after success",
        page.locator("#voice-text").input_value() == "",
    )
    check("the browser reports no page errors", not errors)
    browser.close()
