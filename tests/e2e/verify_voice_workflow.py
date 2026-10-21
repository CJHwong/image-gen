"""Check the single-clip Voice workflow and immediate render feedback."""

import sys

from playwright.sync_api import sync_playwright
from voice_helpers import choose_voice_profile

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("document.getElementById('voice-studio')?.capabilities?.backend_id === 'auk_base'")
    check("Voice starts with AuK", page.locator("#backend-toggle .name").inner_text().strip() == "AuK")
    check("Design starts with no invented voice", page.locator("#voice-description").input_value() == "")
    check("the form has no sentence splitting control", page.locator("#voice-split-sentences").count() == 0)
    check("the field labels have no required suffix", "(required)" not in page.locator("#voice-controls").inner_text())
    check(
        "Generate names both missing inputs",
        "script" in page.locator("#voice-go-sub").inner_text().lower()
        and "voice" in page.locator("#voice-go-sub").inner_text().lower(),
    )
    script = "The first sentence. The second sentence."
    page.locator("#voice-text").fill(script)
    check("typing creates no gallery tile", page.locator("#voice-gallery").is_hidden())
    for name in [
        "Conversation",
        "Narration",
        "Commanding delivery",
        "Dramatic character",
        "Emotional delivery",
        "Voice profile",
    ]:
        page.locator("#voice-templates-toggle").click()
        page.locator("#voice-templates").get_by_role("menuitem", name=name, exact=True).click()
        check(name + " exposes four editable fields", page.locator(".voice-template-field").count() == 4)
        check(name + " supplies a voice description", bool(page.locator("#voice-description").input_value()))
    page.locator("#voice-templates-toggle").click()
    page.get_by_role("menuitem", name="Write your own", exact=True).click()
    check("Write your own clears the description", page.locator("#voice-description").input_value() == "")
    check(
        "Generate indicates the missing voice",
        page.locator("#voice-generate").is_disabled() and "voice" in page.locator("#voice-go-sub").inner_text().lower(),
    )
    choose_voice_profile(page)
    voice = page.locator("#voice-description").input_value()
    waiting = []
    page.route("**/voice/operations", lambda route: waiting.append(route))
    page.locator("#voice-generate").click()
    page.locator(".voice-render-pending").wait_for(state="visible")
    page.wait_for_function("document.getElementById('voice-studio').busy")
    check("Generate shows its placeholder before acceptance", bool(waiting))
    check("the button shows Starting before acceptance", "Starting" in page.locator("#voice-run-labels").inner_text())
    check("Generate switches the preview to generation", page.locator("#voice-generation").is_visible())
    check("there is exactly one placeholder", page.locator("#voice-gallery .frame").count() == 1)
    waiting[0].continue_()
    page.unroute("**/voice/operations")
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 1 && !document.getElementById('voice-studio').locked",
        timeout=120000,
    )
    check("the whole script produces one clip", page.locator(".voice-clip").count() == 1)
    check("the result replaces the placeholder", page.locator(".voice-render-pending").count() == 0)
    check("success clears the script", page.locator("#voice-text").input_value() == "")
    check("success clears the voice", page.locator("#voice-description").input_value() == "")
    check("success clears the template", page.locator("#voice-templates-toggle").inner_text().strip() == "Templates")
    check("the completed script remains in metadata", page.locator(".voice-output-script").inner_text() == script)
    check("the completed voice remains in metadata", voice in page.locator(".voice-output-description").inner_text())
    check(
        "the player uses a simple clip label", page.locator(".audio-preview-heading strong").inner_text() == "Audio 1"
    )
    check("the gallery counts clips", "1 clip" in page.locator("#voice-gallery .strip-head").inner_text())
    check("the selected clip has the shared circle", page.locator(".voice-clip.selected svg.mark path").count() == 1)
    operations = []
    page.on(
        "request",
        lambda request: (
            operations.append(request.url)
            if request.method == "POST" and request.url.endswith("/voice/operations")
            else None
        ),
    )
    page.locator("#voice-track-toggle").click()
    menu = page.locator("#voice-track-menu")
    for name in ["Reuse script and voice", "Send to Video", "Send to Clone"]:
        check(name + " is a menu item", menu.get_by_role("menuitem", name=name, exact=True).count() == 1)
    check(
        "the clip menu has no sentence joining actions",
        menu.get_by_role("menuitem", name="Play joined audio", exact=True).count() == 0,
    )
    menu.get_by_role("menuitem", name="Reuse script and voice", exact=True).click()
    check(
        "reuse restores both inputs",
        page.locator("#voice-text").input_value() == script
        and page.locator("#voice-description").input_value() == voice,
    )
    check("reuse does not generate", not operations)
    page.locator("#voice-track-toggle").click()
    page.get_by_role("menuitem", name="Send to Clone", exact=True).click()
    page.wait_for_function("document.getElementById('voice-studio').mode === 'clone'")
    check(
        "Clone gets the selected clip reference",
        page.evaluate("document.getElementById('voice-studio').reference.duration > 0"),
    )
    check("Record is disabled with a reference", page.get_by_role("button", name="Record", exact=True).is_disabled())
    check(
        "there is no Replace button",
        page.get_by_role("button", name="Replace reference recording", exact=True).count() == 0,
    )
    page.get_by_role("button", name="Clear voice reference", exact=True).click()
    check(
        "clearing restores Add reference",
        page.get_by_role("button", name="Add reference recording", exact=True).is_visible(),
    )
    check("clearing enables Record", page.get_by_role("button", name="Record", exact=True).is_enabled())
    check("Clone handoff does not generate", not operations)
    page.locator('label[for="voice-mode-design"]').click()
    long_script = "This is a long narration. " * 150
    long_voice = "A calm and clear narrator with a steady pace. " * 100
    page.locator("#voice-text").fill(long_script)
    page.locator("#voice-description").fill(long_voice)
    page.route("**/voice/operations", lambda route: route.fulfill(status=503, json={"error": "A test failure."}))
    page.locator("#voice-generate").click()
    page.wait_for_function(
        "!document.getElementById('voice-studio').busy && document.getElementById('voice-studio').error"
    )
    check(
        "failure keeps both inputs",
        page.locator("#voice-text").input_value() == long_script
        and page.locator("#voice-description").input_value() == long_voice,
    )
    page.unroute("**/voice/operations")
    page.locator("#voice-generate").click()
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 2 && !document.getElementById('voice-studio').locked",
        timeout=120000,
    )
    check("a long script also produces one clip", page.locator(".voice-clip").count() == 2)
    for selector in [".voice-output-script", ".voice-output-description"]:
        paragraph = page.locator(selector)
        check(
            selector + " is limited to two lines",
            paragraph.evaluate(
                "node => getComputedStyle(node).webkitLineClamp === '2' && node.getBoundingClientRect().height <= parseFloat(getComputedStyle(node).lineHeight) * 2 + 1"
            ),
        )
        paragraph.click()
        page.locator("#voice-details-sheet").wait_for(state="visible")
        check(selector + " opens its full text", len(page.locator("#voice-details-sheet").inner_text()) > 3000)
        page.keyboard.press("Escape")
    page.evaluate("document.getElementById('voice-studio').saved")
    page.reload()
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 2")
    check("reload preserves completed clips", page.locator(".voice-clip").count() == 2)
    check(
        "reload preserves the cleared form",
        page.locator("#voice-text").input_value() == "" and page.locator("#voice-description").input_value() == "",
    )
    check("the browser reports no errors", not errors)
    browser.close()
