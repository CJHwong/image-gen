"""Check Voice preview layout against the shared Image and Video design."""

import sys

from playwright.sync_api import sync_playwright
from voice_helpers import choose_voice_profile, create_voice_clips

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
    context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("document.getElementById('voice-studio').capabilities.modes.length === 3")
    choose_voice_profile(page)
    check("Voice uses the shared stage", page.locator(".voice-preview-area.stage").count() == 1)
    check(
        "Voice keeps the Image stage surface and text",
        page.evaluate("""() => {
          const image = getComputedStyle(document.getElementById('image-stage'));
          const voice = getComputedStyle(document.querySelector('.voice-preview-area'));
          return ['backgroundColor', 'backgroundImage', 'color'].every(name => image[name] === voice[name]);
        }"""),
    )
    check(
        "the empty stage has no permanent banner",
        page.locator(".voice-stage-head, .voice-kicker, #voice-studio h2").count() == 0,
    )
    empty = page.locator(".voice-empty.video-empty")
    check("Voice uses the shared empty preview", empty.count() == 1)
    check("the empty preview identifies audio", empty.locator(".video-empty-mark").inner_text() == "AUDIO")
    check("the empty preview uses the Preview label", empty.locator("strong").inner_text() == "Preview audio")
    check("empty audio has no transport", page.locator("#voice-track-menu").is_hidden())
    empty.get_by_role("button").click()
    check(
        "the preview action focuses the script",
        page.locator("#voice-text").evaluate("field => field === document.activeElement"),
    )
    page.locator('label[for="voice-mode-edit"]').click()
    check(
        "empty Edit does not ask for a script",
        empty.get_by_role("button", name="Write a script", exact=True).count() == 0,
    )
    check("empty Edit explains the reference", "reference" in empty.inner_text().lower())
    empty.get_by_role("button", name="Describe the change", exact=True).click()
    check(
        "the Edit preview action focuses the instruction",
        page.locator("#voice-text").evaluate("field => field === document.activeElement"),
    )
    page.locator('label[for="voice-mode-design"]').click()
    page.locator("#voice-description").fill(
        "A warm and clear narrator speaks with a calm natural rhythm, gentle expression, "
        "and careful pronunciation for an intimate documentary about people and their everyday lives."
    )
    page.locator("#voice-text").fill("A short preview sentence.")
    page.locator("#voice-generate").click()
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 1 && !document.getElementById('voice-studio').busy"
    )
    check(
        "one audio clip fills the workspace height",
        page.evaluate("""() => {
          const work = document.getElementById('voice-studio').getBoundingClientRect();
          const gallery = document.getElementById('voice-gallery').getBoundingClientRect();
          return Math.abs(work.bottom - gallery.bottom) <= 1;
        }"""),
    )
    for width, height in [(1200, 665), (1440, 1000), (390, 700)]:
        page.set_viewport_size({"width": width, "height": height})
        page.evaluate(
            "async () => { await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame); }"
        )
        geometry = page.locator("#voice-output-details").evaluate("""bar => {
          const style = getComputedStyle(bar);
          const bounds = bar.getBoundingClientRect();
          const about = bar.querySelector('.about').getBoundingClientRect();
          const actions = bar.querySelector('.actions').getBoundingClientRect();
          const buttons = [...bar.querySelectorAll('.actions > button')].filter(button => button.getClientRects().length);
          const description = bar.querySelector('.voice-output-description');
          return {
            transparent: style.backgroundColor === 'rgba(0, 0, 0, 0)' && parseFloat(style.borderTopWidth) === 0,
            sameRow: about.right <= actions.left + 1 && about.top < actions.bottom && actions.top < about.bottom,
            rightAligned: Math.abs(Math.max(...buttons.map(button => button.getBoundingClientRect().right)) - (bounds.right - parseFloat(style.paddingRight))) <= 2,
            wraps: description.getBoundingClientRect().height > parseFloat(getComputedStyle(description).lineHeight) * 1.5,
            icons: buttons.every(button => button.querySelector('svg.icon')),
            oneActionRow: Math.max(...buttons.map(button => button.getBoundingClientRect().top)) - Math.min(...buttons.map(button => button.getBoundingClientRect().top)) <= 2,
            fits: bar.scrollWidth <= bar.clientWidth && document.documentElement.scrollWidth <= innerWidth
          };
        }""")
        check("the metadata keeps the stage surface at " + str(width), geometry["transparent"])
        check("the metadata actions align right at " + str(width), geometry["rightAligned"])
        check("the metadata actions use icons at " + str(width), geometry["icons"])
        check("the metadata fits the viewport at " + str(width), geometry["fits"])
        if width > 390:
            check("the metadata actions keep one desktop row at " + str(width), geometry["oneActionRow"])
            check("the metadata keeps its two desktop columns at " + str(width), geometry["sameRow"])
            check("the voice description wraps at " + str(width), geometry["wraps"])
        else:
            page.locator("#voice-track-toggle").click()
            menu = page.locator("#voice-track-menu").bounding_box()
            check(
                "the phone track menu stays inside the viewport",
                menu["x"] >= 0
                and menu["y"] >= 0
                and menu["x"] + menu["width"] <= width + 1
                and menu["y"] + menu["height"] <= height + 1,
            )
            page.locator("#voice-track-toggle").click()
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator("#voice-gallery").get_by_role("button", name="Clear all", exact=True).click()
    page.locator("#voice-text").fill("First layout sentence. Second layout sentence.")
    header = page.locator("#voice-gallery .strip-head")
    check("a draft script keeps the gallery hidden", page.locator("#voice-gallery").is_hidden())
    check("draft segments create no gallery tiles", page.locator(".voice-clip-pending").count() == 0)
    check("draft segments have no transport", page.locator("#voice-track-menu").is_hidden())
    create_voice_clips(page, ["First layout sentence.", "Second layout sentence."])
    check("completed audio uses the shared compact header", header.count() == 1)
    check("completed clips appear in the header", "2 clips" in header.inner_text())
    check("the compact header leaves space for the preview", header.bounding_box()["height"] <= 48)
    check(
        "the Voice gallery fills the workspace height",
        page.evaluate("""() => {
          const work = document.getElementById('voice-studio').getBoundingClientRect();
          const gallery = document.getElementById('voice-gallery').getBoundingClientRect();
          return Math.abs(work.bottom - gallery.bottom) <= 1;
        }"""),
    )
    check("the action menu stays secondary", page.locator("#voice-track-menu").is_hidden())
    page.locator("#voice-track-toggle").click()
    check("the menu opens normal actions", page.locator("#voice-track-menu").is_visible())
    check(
        "whole clips offer no joined playback",
        page.get_by_role("menuitem", name="Play joined audio", exact=True).count() == 0,
    )
    check(
        "the action menu has no embedded transport",
        page.locator("#voice-track-menu input, #voice-track-menu output").count() == 0,
    )
    page.locator("#voice-track-toggle").click()
    page.set_viewport_size({"width": 390, "height": 700})
    check(
        "the compact Voice layout has no horizontal overflow",
        page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"),
    )
    check("the script keeps both cards on a phone", page.locator(".voice-clip[data-take-id]").count() == 2)
    page.locator("#voice-text").fill("Unfinished layout script.")
    header.get_by_role("button", name="Clear all", exact=True).click()
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 0")
    check(
        "Clear all preserves the script",
        page.locator("#voice-text").input_value() == "Unfinished layout script.",
    )
    check("Clear all hides the empty gallery", page.locator("#voice-gallery").is_hidden())
    check(
        "Clear all retains the current script",
        page.evaluate("document.getElementById('voice-studio').segments.length") == 1,
    )
    check("Clear all creates no gallery draft tiles", page.locator(".voice-clip-pending").count() == 0)
    check("Clear all hides the empty transport", page.locator("#voice-track-menu").is_hidden())
    page.locator("#voice-text").fill("")
    check("an empty script restores the shared preview", empty.is_visible())
    check("an empty script removes the compact header", page.locator("#voice-gallery").is_hidden())
    check(
        "the empty phone preview has no horizontal overflow",
        page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"),
    )
    check("the browser reports no page errors", not errors)
    browser.close()
