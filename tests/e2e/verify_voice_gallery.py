"""Check the single Voice preview and the gallery of retained audio takes."""

import sys

from playwright.sync_api import sync_playwright
from voice_helpers import choose_voice_profile, create_voice_clips, generate_another_take

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
    check("Voice has one main preview pane", page.locator("#voice-preview-pane").count() == 1)
    check("the empty Voice studio has no gallery tiles", page.locator("#voice-gallery .voice-clip").count() == 0)
    page.locator("#voice-text").fill("First gallery sentence." + "a" * 1500 + ".")
    page.locator("#voice-description").fill(page.locator("#voice-description").input_value() + " " + "b" * 1200)
    original_voice = page.locator("#voice-description").input_value()
    page.locator(".voice-advanced summary").click()
    page.locator("#voice-seed").fill("7")
    page.locator("#voice-seconds").fill("4")
    check("typing a script keeps the empty gallery hidden", page.locator("#voice-gallery").is_hidden())
    check("draft sentences create no gallery tiles", page.locator(".voice-clip-pending, .voice-segment").count() == 0)
    page.locator("#voice-generate").click()
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 1 && !document.getElementById('voice-studio').busy"
    )
    create_voice_clips(page, ["Second gallery sentence."])
    gallery = page.locator("#voice-gallery")
    check("the gallery retains both generated clips", gallery.locator(".voice-clip[data-take-id]").count() == 2)
    check("completed clips share the gallery frame style", gallery.locator(".voice-clip.frame").count() == 2)
    check("only the selected clip has the full preview", page.locator("audio-preview#voice-audio-preview").count() == 1)
    first = gallery.get_by_role("button", name="Select audio 1", exact=True)
    second = gallery.get_by_role("button", name="Select audio 2", exact=True)
    first.click()
    check(
        "the selected clip caption shows its sentence",
        "First gallery sentence." in page.locator(".voice-output-script").inner_text(),
    )
    check(
        "gallery selection stays silent",
        page.evaluate(
            "document.getElementById('voice-studio').player.paused && !document.getElementById('voice-audio-preview').playing"
        ),
    )
    metadata = page.locator("#voice-output-details")
    if metadata.locator("summary").count() and not metadata.evaluate("element => element.open"):
        metadata.locator("summary").click()
    original_metadata = metadata.inner_text()
    check(
        "long script and description use two compact lines",
        page.locator(".voice-output-details .prompt-line").evaluate_all("""elements => elements.every(element => {
          const style = getComputedStyle(element);
          return style.webkitLineClamp === '2'
            && element.scrollWidth <= element.clientWidth + 1
            && element.clientHeight <= parseFloat(style.lineHeight) * 2 + 1;
        })"""),
    )
    check(
        "long metadata leaves space for the waveform",
        page.locator("#voice-preview-pane").bounding_box()["height"] >= 300,
    )
    check("clip metadata keeps its original voice description", original_voice in original_metadata)
    check("clip metadata keeps the actual model", "AuK" in original_metadata)
    check("clip metadata keeps the actual seed", "7" in original_metadata)
    page.locator("#voice-description").fill("A different robotic voice for a future clip.")
    page.locator("#voice-seed").fill("999")
    check("sidebar changes cannot rewrite completed metadata", metadata.inner_text() == original_metadata)
    check(
        "the preview has one shared playback control",
        page.locator("#voice-audio-preview button[aria-label='Play']").count() == 1,
    )
    check("full clip editing uses the shared action style", page.locator("#voice-selected-edit.btn.quiet").count() == 1)
    check(
        "full clip downloads use the shared icon action", page.locator("#voice-selected-download.icon-btn").count() == 1
    )
    check("full clip removal uses the shared icon action", page.locator("#voice-selected-remove.icon-btn").count() == 1)
    check("audio details have no separate Info action", page.locator("#voice-selected-info").count() == 0)
    page.set_viewport_size({"width": 390, "height": 700})
    page.locator(".voice-output-description").click()
    sheet = page.locator("#voice-details-sheet")
    check(
        "clip details open an accessible sheet",
        sheet.is_visible()
        and sheet.get_attribute("role") == "region"
        and sheet.get_attribute("aria-label") == "Audio details",
    )
    check("clip details keep the complete long voice description", original_voice in sheet.inner_text())
    check("clip details keep the original script", "First gallery sentence." in sheet.inner_text())
    check(
        "unbroken metadata fits the phone details sheet",
        sheet.evaluate("element => element.scrollWidth <= element.clientWidth"),
    )
    check(
        "unbroken metadata wraps inside its fields",
        sheet.locator("dd").evaluate_all("fields => fields.every(field => field.scrollWidth <= field.clientWidth)"),
    )
    page.keyboard.press("Escape")
    check(
        "Escape restores focus to clip details",
        sheet.is_hidden()
        and page.locator(".voice-output-description").evaluate("button => button === document.activeElement"),
    )
    page.locator(".voice-output-description").press("Enter")
    check("the description opens details from the keyboard", sheet.is_visible())
    page.locator("#voice-details-close").click()
    check("the details close control returns to the preview", sheet.is_hidden())
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.evaluate("""async () => {
      document.getElementById('voice-audio-preview').querySelector('button[aria-label="Play"]').click();
      document.querySelector('.voice-clip[aria-label="Select audio 2"]').click();
      await new Promise(requestAnimationFrame);
      await new Promise(requestAnimationFrame);
    }""")
    check(
        "rapid playback then selection has no stale error",
        not page.evaluate("document.getElementById('voice-studio').error"),
    )
    tiles = gallery.locator(".voice-clip")
    tiles.first.click()
    tiles.first.focus()
    tiles.first.press("ArrowRight")
    check("the gallery supports keyboard selection", tiles.nth(1).get_attribute("aria-pressed") == "true")
    tiles.nth(1).press("ArrowLeft")
    check("the gallery returns to the previous clip", tiles.first.get_attribute("aria-pressed") == "true")
    tiles.first.press("End")
    check(
        "End selects the last gallery clip", gallery.locator(".voice-clip").last.get_attribute("aria-pressed") == "true"
    )
    gallery.locator(".voice-clip").last.press("Home")
    check(
        "Home selects the first gallery clip",
        gallery.locator(".voice-clip").first.get_attribute("aria-pressed") == "true",
    )
    first.click()
    generate_another_take(page)
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 3")
    check("a retake keeps every gallery clip", gallery.locator(".voice-clip[data-take-id]").count() == 3)
    first.click()
    page.wait_for_function("document.getElementById('voice-audio-preview').duration > .7")
    start = page.locator("#voice-audio-preview").get_by_role("spinbutton", name="Selection start", exact=True)
    start.fill("0.2")
    start.press("Tab")
    gallery.get_by_role("button", name="Select audio 3", exact=True).click()
    page.wait_for_function("document.getElementById('voice-audio-preview').start === 0")
    check("a gallery change resets the prior range", float(start.input_value()) == 0)
    check("joined playback stays secondary", page.locator("#voice-track-menu").is_hidden())
    page.locator("#voice-track-toggle").click()
    check("the track toggle opens joined controls", page.locator("#voice-track-menu").is_visible())
    page.locator("#voice-track-toggle").click()
    check("the track toggle closes joined controls", page.locator("#voice-track-menu").is_hidden())
    page.locator("#voice-selected-remove").click()
    check("removing one clip keeps the other clips", gallery.locator(".voice-clip[data-take-id]").count() == 2)
    check(
        "removing one clip keeps both sentences",
        page.evaluate("document.getElementById('voice-studio').segments.length") == 2,
    )
    old_ids = gallery.locator(".voice-clip").evaluate_all("tiles => tiles.map(tile => tile.dataset.takeId)")
    first_id = first.get_attribute("data-take-id")
    choose_voice_profile(page)
    page.locator("#voice-text").fill("A third gallery sentence.")
    check("a new script preserves generated gallery clips", gallery.locator(".voice-clip[data-take-id]").count() == 2)
    check("a new script creates no gallery draft tiles", gallery.locator(".voice-clip-pending").count() == 0)
    check(
        "the joined track excludes clips from an older script",
        page.evaluate("document.getElementById('voice-studio').selectedTakes.length") == 0,
    )
    check(
        "history alone does not offer joined track actions",
        page.get_by_role("menuitem", name="Play joined audio", exact=True).count() == 0,
    )
    gallery.locator(f'.voice-clip[data-take-id="{first_id}"]').click()
    page.evaluate("document.getElementById('voice-studio').saved")
    page.reload()
    page.wait_for_function(
        "!document.getElementById('voice-studio').loading && document.getElementById('voice-studio').capabilities.modes.length === 3"
    )
    check(
        "the completed gallery selection survives reload",
        gallery.locator(f'.voice-clip[data-take-id="{first_id}"]').get_attribute("aria-pressed") == "true",
    )
    check("the draft script survives reload", page.locator("#voice-text").input_value() == "A third gallery sentence.")
    check("restored drafts create no gallery tiles", page.locator(".voice-clip-pending").count() == 0)
    gallery.locator(f'.voice-clip[data-take-id="{first_id}"]').click()
    check(
        "history keeps the original script metadata",
        "First gallery sentence." in page.locator(".voice-output-script").inner_text(),
    )
    with page.expect_request(
        lambda request: request.method == "POST" and request.url.endswith("/voice/operations")
    ) as pending:
        page.locator("#voice-generate").click()
    check(
        "Generate targets only the new script",
        pending.value.post_data_json.get("text") == "A third gallery sentence."
        and "items" not in pending.value.post_data_json,
    )
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 3")
    check(
        "new audio keeps every previous gallery clip",
        set(old_ids).issubset(
            set(gallery.locator(".voice-clip").evaluate_all("tiles => tiles.map(tile => tile.dataset.takeId)"))
        ),
    )
    check("a successful generation clears its script", page.locator("#voice-text").input_value() == "")
    choose_voice_profile(page)
    page.locator("#voice-text").fill("A third gallery sentence.")
    gallery.locator(f'.voice-clip[data-take-id="{old_ids[0]}"]').click()
    page.locator("#voice-selected-remove").click()
    check(
        "removing history does not leave a pending history tile",
        page.evaluate(
            "document.getElementById('voice-studio').segments.every(segment => segment.inScript !== false || segment.takes.length > 0)"
        ),
    )
    page.evaluate("document.getElementById('voice-studio').saved")
    check(
        "saved removal cannot restore empty history",
        page.evaluate("""async () => {
          const {loadVoice} = await import('/page/lib/voice-store.js');
          const stored = await loadVoice();
          return stored.segments.every(segment => segment.inScript !== false || segment.takes.length > 0);
        }"""),
    )
    page.reload()
    page.wait_for_function("!document.getElementById('voice-studio').loading")
    check(
        "reload cannot restore empty history",
        page.evaluate(
            "document.getElementById('voice-studio').segments.every(segment => segment.inScript !== false || segment.takes.length > 0)"
        ),
    )
    gallery.get_by_role("button", name="Clear all", exact=True).click()
    check(
        "Clear all removes empty history segments",
        page.evaluate("document.getElementById('voice-studio').segments.every(segment => segment.inScript !== false)"),
    )
    check(
        "Clear all hides the gallery and keeps the current script",
        gallery.is_hidden()
        and page.locator(".voice-clip-pending").count() == 0
        and page.locator("#voice-text").input_value() == "A third gallery sentence.",
    )
    response = context.request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "voice",
            "backend": "auk",
            "mode": "design",
            "text": "This recording comes from the API.",
            "voice": original_voice,
            "seconds": 4,
        },
    )
    check("an external API recording starts", response.status == 202)
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 1")
    check(
        "an external recording keeps the current script",
        page.locator("#voice-text").input_value() == "A third gallery sentence.",
    )
    check(
        "an external recording stays outside the joined script",
        page.evaluate("document.getElementById('voice-studio').selectedTakes.length") == 0,
    )
    page.wait_for_function("!document.getElementById('voice-studio').activeOperation")
    page.locator("#voice-audio-preview").get_by_role("button", name="Play", exact=True).click()
    page.wait_for_function("document.getElementById('voice-audio-preview').playing")
    response = context.request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "voice",
            "backend": "auk",
            "mode": "design",
            "text": "A newer imported recording selects its own preview.",
            "voice": original_voice,
            "seconds": 1,
        },
    )
    check("a second external recording starts", response.status == 202)
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 2")
    check(
        "a newly selected API result stops the old full clip",
        page.evaluate("!document.getElementById('voice-audio-preview').playing"),
    )
    page.locator("#voice-text").fill("")
    check(
        "history without a current script asks for a script",
        page.locator("#voice-generate").is_disabled()
        and "Write a script" in page.locator("#voice-go-sub").inner_text(),
    )
    check(
        "history without a current script has no joined track actions",
        page.get_by_role("menuitem", name="Play joined audio", exact=True).count() == 0,
    )
    page.set_viewport_size({"width": 390, "height": 700})
    check("the phone layout keeps one main preview", page.locator("#voice-preview-pane").count() == 1)
    check("the phone layout has no page overflow", page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    page.evaluate("""async () => {
      const voice = document.getElementById('voice-studio');
      const stored = voice.snapshot();
      const pending = {id:'legacy-pending-selection', text:'An unfinished legacy script.', takes:[], selected:null, inScript:true};
      voice.adopt({...stored, mode:'design', script:pending.text, selectedId:'pending:' + pending.id,
        segments:[pending, ...stored.segments.map(segment => ({...segment, inScript:false}))]});
      await voice.saved;
    }""")
    page.reload()
    page.wait_for_function(
        "!document.getElementById('voice-studio').loading && document.getElementById('voice-studio').takesCount === 2"
    )
    check("a legacy draft selection cannot hide completed audio", page.locator("#voice-audio-preview").count() == 1)
    check("a legacy draft still creates no gallery tile", page.locator(".voice-clip-pending").count() == 0)
    check(
        "the legacy draft survives reload", page.locator("#voice-text").input_value() == "An unfinished legacy script."
    )
    check("the browser reports no page errors", not errors)
    browser.close()
