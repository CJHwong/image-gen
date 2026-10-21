"""Check shared Voice controls against a fresh studio stub server."""

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
    context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("document.getElementById('voice-studio').capabilities.modes.length === 3")
    check("Voice uses the shared run component", page.locator("#voice-generate > run-button").count() == 1)
    check(
        "all workspaces use the shared run style",
        page.locator("#go.run-button, #video-generate.run-button, #voice-generate.run-button").count() == 3,
    )
    modes = page.get_by_role("radiogroup", name="Voice mode", exact=True)
    check("Voice uses native mode radios", modes.locator('input[type="radio"][name="voice-mode"]').count() == 3)
    check("Design starts selected", page.locator("#voice-mode-design").is_checked())
    check("Design uses the Generate verb", page.locator("#voice-run-labels").inner_text() == "Generate")
    check("the footer uses the shared caption classes", page.locator("#voice-go-sub.sub.num").count() == 1)
    page.locator('label[for="voice-mode-clone"]').click()
    check("Clone uses the Generate verb", page.locator("#voice-run-labels").inner_text() == "Generate")
    check(
        "Voice reuses the reference dropzone style",
        page.locator("#voice-reference-choose.refs .refs-empty").count() == 1,
    )
    check("the native audio input stays hidden", page.locator("#voice-reference").is_hidden())
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Add reference recording", exact=True).click()
    check(
        "the reference dropzone opens the audio chooser", chooser.value.element.get_attribute("id") == "voice-reference"
    )
    page.locator('label[for="voice-mode-edit"]').click()
    check("Edit uses the Edit verb", page.locator("#voice-run-labels").inner_text() == "Edit")
    check("Edit marks its native radio selected", page.locator("#voice-mode-edit").is_checked())
    check(
        "Edit labels its instruction consistently",
        page.locator('label[for="voice-text"]').inner_text() == "What to change",
    )
    toggle = page.locator("#voice-templates-toggle")
    check(
        "Templates shares the instruction header",
        toggle.locator('xpath=ancestor::div[contains(@class,"field-head")]').locator('label[for="voice-text"]').count()
        == 1,
    )
    check("Templates uses the shared pill style", "pill" in toggle.get_attribute("class").split())
    toggle.click()
    menu = page.locator("#voice-templates")
    check("Templates opens the shared menu", menu.is_visible() and toggle.get_attribute("aria-expanded") == "true")
    bounds = menu.bounding_box()
    panel = page.locator("#voice-controls").bounding_box()
    check(
        "Templates stays inside the sidebar",
        bounds["x"] >= panel["x"] and bounds["x"] + bounds["width"] <= panel["x"] + panel["width"],
    )
    check("Templates stays inside the viewport", bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 1000)
    check("a long Templates menu can scroll", menu.evaluate("menu => getComputedStyle(menu).overflowY") == "auto")
    items = menu.get_by_role("menuitem")
    check("opening Templates focuses its first item", items.first.evaluate("item => item === document.activeElement"))
    page.keyboard.press("ArrowDown")
    check("ArrowDown moves template focus", items.nth(1).evaluate("item => item === document.activeElement"))
    page.keyboard.press("Escape")
    check(
        "Escape closes Templates and restores focus",
        menu.is_hidden() and toggle.evaluate("button => button === document.activeElement"),
    )
    toggle.click()
    items.last.scroll_into_view_if_needed()
    last_bounds = items.last.bounding_box()
    check(
        "the last template stays reachable", last_bounds["y"] >= 0 and last_bounds["y"] + last_bounds["height"] <= 1000
    )
    check(
        "the sidebar does not clip the last template",
        items.last.evaluate("""item => {
          const bounds = item.getBoundingClientRect();
          return document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2)?.closest('button') === item;
        }"""),
    )
    page.keyboard.press("Escape")
    toggle.click()
    menu.get_by_role("menuitem", name="Speed", exact=True).click()
    check("a template closes its menu", menu.is_hidden() and toggle.get_attribute("aria-expanded") == "false")
    check("Speed keeps its selected default", page.locator(".voice-template-field select").input_value() == "1.5")
    check(
        "Templates fills the main instruction",
        page.locator("#voice-text").input_value() == "Adjust the speech speed to 1.5x.",
    )
    page.locator(".voice-template-field select").select_option("2.0")
    check(
        "a template field updates the main instruction",
        page.locator("#voice-text").input_value() == "Adjust the speech speed to 2.0x.",
    )
    page.locator("#voice-text").fill("Make the voice warmer.")
    check("a manual instruction stays intact", page.locator("#voice-text").input_value() == "Make the voice warmer.")
    check("a manual instruction clears the template", page.locator(".voice-template-field").count() == 0)
    page.locator("#voice-text").fill("")
    page.locator("#voice-text").press_sequentially("Keep the voice warm and clear.", delay=35)
    check(
        "slow custom typing preserves spaces",
        page.locator("#voice-text").input_value() == "Keep the voice warm and clear.",
    )
    toggle.click()
    menu.get_by_role("menuitem", name="Speed", exact=True).click()
    toggle.click()
    menu.get_by_role("menuitem", name="Custom instruction", exact=True).click()
    check("Custom instruction clears the selected template", page.locator(".voice-template-field").count() == 0)
    toggle.click()
    page.locator('label[for="voice-text"]').click()
    check("an outside click closes Templates", menu.is_hidden())
    advanced = page.locator(".voice-advanced")
    advanced.locator("summary").click()
    check("Advanced uses the shared layout", advanced.locator(".advanced .field").count() == 3)
    check("Advanced shows a summary", advanced.locator("summary .values.num").count() == 1)
    page.locator('label[for="voice-mode-design"]').click()
    choose_voice_profile(page)
    page.locator("#voice-text").fill("The shared Generate button creates this take.")
    page.locator("#voice-generate").click()
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 1 && !document.getElementById('voice-studio').locked"
    )
    check("Generate creates a take", page.locator(".voice-clip[data-take-id]").count() == 1)
    page.locator("#voice-selected-edit").click()
    page.wait_for_function(
        "document.getElementById('voice-studio').mode === 'edit' && document.getElementById('voice-studio').reference"
    )
    page.locator("#voice-text").fill("Make the voice warmer.")
    page.locator("#voice-generate").click()
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 2 && !document.getElementById('voice-studio').locked"
    )
    check("Edit preserves the original take", page.locator(".voice-clip[data-take-id]").count() == 2)
    page.locator('label[for="voice-mode-design"]').click()
    choose_voice_profile(page)
    page.locator("#voice-text").fill("Cancel this continuous recording.")
    page.locator("#voice-generate").click()
    page.wait_for_function("document.getElementById('voice-run-labels').getAttribute('data-state') === 'busy'")
    check("a running operation uses Cancel", page.locator("#voice-run-labels").inner_text() == "Cancel")
    check("a running operation locks every mode", modes.locator("input:disabled").count() == 3)
    cancellations = []
    page.route("**/api/v1/operations/*/cancel", lambda route: cancellations.append(route))
    page.locator("#voice-generate").click()
    page.wait_for_function("document.getElementById('voice-run-labels').getAttribute('data-state') === 'stopping'")
    check("the shared stopping label stays consistent", page.locator("#voice-run-labels").inner_text() == "Stopping…")
    check("Stopping prevents a second cancellation", page.locator("#voice-generate").is_disabled())
    check("Cancel sends one request", len(cancellations) == 1)
    cancellations[0].continue_()
    page.wait_for_function("!document.getElementById('voice-studio').busy")
    check("cancellation restores Generate", page.locator("#voice-run-labels").inner_text() == "Generate")
    check("the browser reports no page errors", not errors)
    for width, height in [(900, 600), (390, 700)]:
        compact = browser.new_context(viewport={"width": width, "height": height})
        narrow = compact.new_page()
        narrow.goto(URL + "/?workspace=voice")
        narrow.wait_for_function("document.getElementById('voice-studio').capabilities.modes.length === 3")
        narrow.locator('label[for="voice-mode-edit"]').click()
        narrow.locator("#voice-templates-toggle").click()
        compact_menu = narrow.locator("#voice-templates")
        bounds = compact_menu.bounding_box()
        check(
            f"Templates opens inside a {width} by {height} viewport",
            bounds["x"] >= 0
            and bounds["y"] >= 0
            and bounds["x"] + bounds["width"] <= width
            and bounds["y"] + bounds["height"] <= height,
        )
        compact_menu.get_by_role("menuitem").first.focus()
        for _ in range(compact_menu.get_by_role("menuitem").count() - 1):
            narrow.keyboard.press("ArrowDown")
        check(
            f"the keyboard reaches the last template at {width} by {height}",
            compact_menu.get_by_role("menuitem").last.evaluate("item => item === document.activeElement"),
        )
        bounds = compact_menu.get_by_role("menuitem").last.bounding_box()
        check(
            f"the last template stays reachable at {width} by {height}",
            bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= height,
        )
        check(
            f"the sidebar does not clip the last template at {width} by {height}",
            compact_menu.get_by_role("menuitem").last.evaluate("""item => {
              const bounds = item.getBoundingClientRect();
              return document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2)?.closest('button') === item;
            }"""),
        )
        compact.close()
    browser.close()
