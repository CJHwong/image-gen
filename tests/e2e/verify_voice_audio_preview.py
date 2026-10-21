"""Check Voice range selection and explicit audio handoffs on the studio stub."""

import base64
import io
import sys
import wave

from playwright.sync_api import sync_playwright
from voice_helpers import choose_voice_profile, generate_another_take

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


def frames(encoded):
    with wave.open(io.BytesIO(base64.b64decode(encoded)), "rb") as audio:
        return audio.readframes(audio.getnframes()), audio.getframerate(), audio.getnframes()


def set_range(preview, start, end):
    for label, value in [("Selection start", start), ("Selection end", end)]:
        field = preview.get_by_role("spinbutton", name=label, exact=True)
        field.fill(str(value))
        field.press("Tab")


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("document.getElementById('voice-studio').capabilities.modes.length === 3")
    choose_voice_profile(page)
    page.locator("#voice-text").fill("Keep this voice take for the audio handoff.")
    page.locator("#voice-generate").click()
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 1 && !document.getElementById('voice-studio').locked"
    )
    check("a Voice take has the shared audio preview", page.locator("audio-preview#voice-audio-preview").count() == 1)
    preview = page.locator("#voice-audio-preview")
    page.wait_for_function("document.getElementById('voice-audio-preview').duration > .7")
    set_range(preview, 0.2, 0.7)
    preview.get_by_role("slider", name="Playback position", exact=True).evaluate(
        "input => { input.value = '.3'; input.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    check("the preview contains one Play control", preview.get_by_role("button", name="Play", exact=True).count() == 1)
    check("the metadata has no second Play control", page.locator("#voice-selected-play").count() == 0)
    check(
        "the player contains no handoff actions",
        preview.get_by_role("button", name="Send to Video", exact=True).count() == 0
        and preview.get_by_role("button", name="Edit", exact=True).count() == 0
        and preview.get_by_role("button", name="Download audio", exact=True).count() == 0,
    )
    check(
        "the metadata contains one set of handoff actions",
        all(
            page.locator(selector).count() == 1
            for selector in ["#voice-selected-video", "#voice-selected-edit", "#voice-selected-download"]
        ),
    )
    preview.get_by_role("button", name="Play", exact=True).click()
    page.wait_for_function("document.getElementById('voice-audio-preview').playing")
    page.wait_for_function("document.getElementById('voice-audio-preview')._player?.readyState >= 1")
    check(
        "Play honors the trim range",
        abs(page.evaluate("document.getElementById('voice-audio-preview')._player.duration") - 0.5) < 0.01,
    )
    waveform = preview.locator(".audio-preview-wave")
    bounds = waveform.bounding_box()
    waveform.click(position={"x": bounds["width"] * 0.4, "y": bounds["height"] / 2})
    check(
        "a waveform seek changes the audible player's position",
        page.evaluate("Math.abs(document.getElementById('voice-audio-preview')._player.currentTime - .2) < .08"),
    )
    preview.get_by_role("button", name="Pause", exact=True).click()
    page.wait_for_function("!document.getElementById('voice-audio-preview').playing")
    check("Pause restores the single Play action", preview.get_by_role("button", name="Play", exact=True).is_visible())
    preview.get_by_role("slider", name="Playback position", exact=True).evaluate(
        "input => { input.value = '.5'; input.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    preview.get_by_role("button", name="Play", exact=True).click()
    page.wait_for_function("document.getElementById('voice-audio-preview').playing")
    page.wait_for_function("!document.getElementById('voice-audio-preview').playing")
    check(
        "natural completion restores the single Play action",
        preview.get_by_role("button", name="Play", exact=True).is_visible(),
    )
    page.locator("#voice-gallery .voice-clip").first.focus()
    page.keyboard.press("Space")
    page.wait_for_function("document.getElementById('voice-audio-preview').playing")
    check("Space plays the selected preview", page.evaluate("document.getElementById('voice-studio').player.paused"))
    page.keyboard.press("Space")
    page.wait_for_function("!document.getElementById('voice-audio-preview').playing")
    check("Space pauses the selected preview", True)
    original = page.evaluate("""async () => {
      const {blobBase64} = await import('/page/lib/voice-audio.js');
      return blobBase64(document.getElementById('voice-audio-preview').blob);
    }""")
    original_frames, rate, _ = frames(original)
    set_range(preview, 0.2, 0.7)
    operations = []
    page.on(
        "request",
        lambda request: (
            operations.append(request.url)
            if request.method == "POST" and request.url.endswith(("/voice/operations", "/video/operations"))
            else None
        ),
    )
    page.locator("#voice-track-toggle").click()
    page.locator("#voice-selected-clone").click()
    page.wait_for_function("document.getElementById('voice-studio').mode === 'clone'")
    clone_reference = page.evaluate("""async () => {
      const {blobBase64} = await import('/page/lib/voice-audio.js');
      return blobBase64(document.getElementById('voice-studio').reference.blob);
    }""")
    clone_frames, clone_rate, clone_count = frames(clone_reference)
    check(
        "Send to Clone keeps the exact selected audio",
        clone_rate == rate
        and clone_count == round(0.5 * rate)
        and clone_frames == original_frames[round(0.2 * rate) * 2 : round(0.7 * rate) * 2],
    )
    check("Send to Clone does not generate audio", not operations)
    page.locator("#voice-track-toggle").click()
    page.locator("#voice-selected-video").click()
    page.wait_for_function("document.getElementById('media-video-mode').getAttribute('aria-pressed') === 'true'")
    check("Send to Video selects Generate mode", page.locator("#video-mode-generate").is_checked())
    transferred = page.evaluate("document.getElementById('video-studio').audioPayload()")
    audio_frames, audio_rate, audio_count = frames(transferred["data"])
    check(
        "Send to Video keeps the exact selected audio",
        audio_rate == rate
        and audio_count == round(0.5 * rate)
        and audio_frames == original_frames[round(0.2 * rate) * 2 : round(0.7 * rate) * 2],
    )
    check("Send to Video does not generate a video", not operations)
    page.get_by_role("button", name="Voice", exact=True).click()
    page.wait_for_function("document.getElementById('media-voice-mode').getAttribute('aria-pressed') === 'true'")
    page.locator("#voice-track-toggle").click()
    page.locator("#voice-selected-video").click()
    page.wait_for_function("Boolean(document.getElementById('voice-studio').error)")
    check(
        "an existing Video reference requires an explicit clear",
        any(word in page.locator(".voice-error").inner_text().lower() for word in ["clear", "remove"]),
    )
    check(
        "a refused handoff preserves Video audio",
        page.evaluate("document.getElementById('video-studio').audioPayload()") == transferred,
    )
    check(
        "a refused handoff keeps Voice selected",
        page.locator("#media-voice-mode").get_attribute("aria-pressed") == "true",
    )
    duration = page.evaluate("document.getElementById('voice-audio-preview').duration")
    set_range(preview, 0, duration)
    page.locator("#voice-selected-edit").click()
    page.wait_for_function("document.getElementById('voice-studio').mode === 'edit'")
    check(
        "a whole clip edit retains its original segment link",
        page.evaluate("""(() => {
          const voice = document.getElementById('voice-studio');
          return voice.editSegmentId === voice.previewItem.segment.id && voice.reference.blob === voice.previewItem.take.blob;
        })()"""),
    )
    set_range(preview, 0.2, 0.7)
    page.locator("#voice-selected-edit").click()
    page.wait_for_function(
        "document.getElementById('voice-studio').mode === 'edit' && Math.abs(document.getElementById('voice-studio').reference?.duration - .5) < .001"
    )
    check(
        "Edit selection uses only the selected duration",
        abs(page.evaluate("document.getElementById('voice-studio').reference.duration") - 0.5) < 0.001,
    )
    edited_reference = page.evaluate("""async () => {
      const {blobBase64} = await import('/page/lib/voice-audio.js');
      return blobBase64(document.getElementById('voice-studio').reference.blob);
    }""")
    check("Edit selection preserves the crop PCM", frames(edited_reference)[0] == audio_frames)
    check("Edit selection preserves the original take", page.locator(".voice-clip[data-take-id]").count() == 1)
    check(
        "Edit selection does not claim the complete original sentence",
        page.evaluate("document.getElementById('voice-studio').editSegmentId === null"),
    )
    check("Edit selection requires an explicit run", not operations)
    page.locator('label[for="voice-mode-design"]').click()
    held = []
    page.route("**/voice/operations", lambda route: held.append(route))
    with page.expect_request("**/voice/operations"):
        generate_another_take(page)
    page.locator("#voice-generation").wait_for(state="visible")
    check("a Voice operation replaces playback with generation", page.locator("#voice-audio-preview").count() == 0)
    page.get_by_role("button", name="Select audio 1", exact=True).click()
    page.wait_for_function(
        "document.getElementById('voice-studio').previewReady && document.getElementById('voice-audio-preview')?.locked"
    )
    check(
        "browsing an older clip keeps its handoffs locked",
        page.locator("#voice-selected-video").is_disabled() and page.locator("#voice-selected-edit").is_disabled(),
    )
    check("browsing an older clip keeps downloads available", page.locator("#voice-selected-download").is_enabled())
    page.get_by_role("button", name="Show audio generation", exact=True).click()
    page.locator("#voice-generation").wait_for(state="visible")
    held[0].continue_()
    page.unroute("**/voice/operations")
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 2 && !document.getElementById('voice-studio').locked"
    )
    page.get_by_role("button", name="Select audio 1", exact=True).click()
    page.wait_for_function("document.getElementById('voice-audio-preview').duration > 0")
    set_range(preview, 0.2, 0.7)
    page.get_by_role("button", name="Select audio 2", exact=True).click()
    page.wait_for_function("document.getElementById('voice-audio-preview').start === 0")
    check(
        "a different take resets the old selection",
        page.evaluate(
            "document.getElementById('voice-audio-preview').end === document.getElementById('voice-audio-preview').duration"
        ),
    )
    check(
        "take selection does not start playback",
        not page.evaluate("document.getElementById('voice-audio-preview').playing"),
    )
    page.wait_for_function(
        "document.getElementById('voice-audio-preview').duration > 0 && !document.getElementById('voice-studio').busy"
    )
    page.get_by_role("button", name="Video", exact=True).click()
    page.locator("#video-audios .video-audio-remove").click()
    page.get_by_role("button", name="Voice", exact=True).click()
    page.wait_for_function("document.getElementById('voice-audio-preview').duration > .6")
    set_range(preview, 0.1, 0.6)
    delayed = []
    page.route("**/api/v1/audio/trim", lambda route: delayed.append(route))
    with page.expect_request("**/api/v1/audio/trim"):
        page.locator("#voice-track-toggle").click()
        page.locator("#voice-selected-video").click()
    page.get_by_role("button", name="Image", exact=True).click()
    delayed[0].continue_()
    page.unroute("**/api/v1/audio/trim")
    page.wait_for_function("!document.getElementById('voice-audio-preview').busy")
    check(
        "a delayed audio handoff keeps the current workspace",
        page.locator("#media-image-mode").get_attribute("aria-pressed") == "true",
    )
    check(
        "a delayed audio handoff cannot set Video audio",
        page.evaluate("document.getElementById('video-studio').audio === null"),
    )
    page.get_by_role("button", name="Voice", exact=True).click()
    page.set_viewport_size({"width": 390, "height": 700})
    check(
        "the Voice preview has no phone overflow", page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    )
    check("the browser reports no page errors", not errors)
    browser.close()
