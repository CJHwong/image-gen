"""Check audio ranges, exact PCM crops, playback, locks, and stale requests."""

import base64
import io
import math
import struct
import sys
import wave

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


def recording(seconds):
    buffer = io.BytesIO()
    samples = b"".join(
        struct.pack("<h", int(12000 * math.sin(index * math.tau * 220 / 24000)))
        for index in range(round(seconds * 24000))
    )
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(samples)
    return buffer.getvalue(), samples


def set_range(preview, start, end):
    preview.get_by_role("spinbutton", name="Selection start", exact=True).fill(str(start))
    preview.get_by_role("spinbutton", name="Selection start", exact=True).press("Tab")
    preview.get_by_role("spinbutton", name="Selection end", exact=True).fill(str(end))
    preview.get_by_role("spinbutton", name="Selection end", exact=True).press("Tab")


source, samples = recording(1)
second, _ = recording(2)
with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("document.getElementById('voice-studio').capabilities.modes.length === 3")
    page.evaluate(
        """async encoded => {
      await import('/page/components/audio-preview.js');
      const preview = document.createElement('audio-preview');
      preview.id = 'isolated-audio-preview';
      preview.style.cssText = 'position:fixed;left:20px;top:80px;width:600px;max-width:calc(100vw - 40px);z-index:1000';
      preview.label = 'A deterministic recording';
      preview.downloadText = 'Morning river narration';
      preview.downloadAt = 1792555200000;
      preview.downloadId = 'voice-filename-test';
      preview.blob = new Blob([Uint8Array.from(atob(encoded), letter => letter.charCodeAt(0))], {type:'audio/wav'});
      window.previewActions = [];
      window.previewStates = [];
      preview.addEventListener('audio-preview-action', event => window.previewActions.push(event.detail));
      preview.addEventListener('audio-preview-state', event => window.previewStates.push(event.detail));
      document.body.append(preview);
    }""",
        base64.b64encode(source).decode(),
    )
    preview = page.locator("#isolated-audio-preview")
    page.wait_for_function("Math.abs(document.getElementById('isolated-audio-preview').duration - 1) < 1 / 24000")
    speed = preview.get_by_role("combobox", name="Playback speed", exact=True)
    check("the player starts at normal speed", speed.input_value() == "1")
    speed.select_option("2")
    preview.get_by_role("button", name="Play", exact=True).click()
    page.wait_for_function("document.getElementById('isolated-audio-preview')._player?.playbackRate === 2")
    check("the actual player uses double speed", True)
    speed.select_option("1.5")
    check(
        "speed changes apply during playback",
        page.evaluate("document.getElementById('isolated-audio-preview')._player.playbackRate") == 1.5,
    )
    preview.get_by_role("button", name="Pause", exact=True).click()
    speed.select_option("1")
    check("the waveform includes a time ruler", preview.locator(".audio-preview-ruler").is_visible())
    check(
        "the player shares one control row",
        preview.locator(".audio-preview-controls > .audio-preview-player").count() == 1,
    )
    check(
        "the player avoids a nested card",
        preview.locator(".audio-preview").evaluate(
            "node => getComputedStyle(node).backgroundColor === 'rgba(0, 0, 0, 0)' && parseFloat(getComputedStyle(node).borderTopWidth) === 0"
        ),
    )
    check("the preview decodes the complete source", preview.locator("svg").count() > 0)
    check(
        "the preview exposes one playback action",
        page.evaluate("typeof document.getElementById('isolated-audio-preview').play === 'function'"),
    )
    check("the preview has one Play control", preview.get_by_role("button", name="Play", exact=True).count() == 1)
    check(
        "the playback icon keeps its complete drawing bounds",
        preview.get_by_role("button", name="Play", exact=True).locator("svg").get_attribute("viewBox") == "0 0 24 24",
    )
    check(
        "the preview has no handoff controls",
        preview.get_by_role("button").count() == 1,
    )
    for intent in ["play", "pause", "source"]:
        page.evaluate(
            """({encoded, intent}) => {
          const bytes = Uint8Array.from(atob(encoded), letter => letter.charCodeAt(0));
          const original = Blob.prototype.arrayBuffer;
          Blob.prototype.arrayBuffer = async function() {
            Blob.prototype.arrayBuffer = original;
            await new Promise(resolve => window.releasePreviewDecode = resolve);
            return original.call(this);
          };
          const pending = document.createElement('audio-preview');
          pending.id = 'pending-audio-preview';
          pending.blob = new Blob([bytes], {type:'audio/wav'});
          document.body.append(pending);
          window.pendingPreviewPlay = pending.play();
          window.pendingPreviewIntent = intent;
        }""",
            {"encoded": base64.b64encode(source).decode(), "intent": intent},
        )
        page.wait_for_function("typeof window.releasePreviewDecode === 'function'")
        page.evaluate(
            """async () => {
          const pending = document.getElementById('pending-audio-preview');
          if (window.pendingPreviewIntent === 'pause') pending.pause();
          if (window.pendingPreviewIntent === 'source') pending.blob = pending.blob.slice();
          window.releasePreviewDecode();
          delete window.releasePreviewDecode;
          await window.pendingPreviewPlay;
        }"""
        )
        check(
            "a held decode respects the " + intent + " intent",
            page.evaluate("document.getElementById('pending-audio-preview').playing") == (intent == "play"),
        )
        page.evaluate("document.getElementById('pending-audio-preview').remove()")
    with page.expect_download() as complete_download:
        page.evaluate("void document.getElementById('isolated-audio-preview').action('download')")
    check(
        "a whole recording download preserves its original bytes", complete_download.value.path().read_bytes() == source
    )
    whole_name = complete_download.value.suggested_filename
    check(
        "the whole audio filename describes the script",
        whole_name.startswith("audio-morning-river-narration-") and whole_name.endswith(".wav"),
    )
    set_range(preview, 0.2, 0.7)
    waveform = preview.locator(".audio-preview-wave")
    bounds = waveform.bounding_box()
    waveform.click(position={"x": bounds["width"] * 0.45, "y": bounds["height"] * 0.5})
    check(
        "a waveform click preserves the trim range",
        preview.get_by_role("spinbutton", name="Selection start", exact=True).input_value() == "0.20"
        and preview.get_by_role("spinbutton", name="Selection end", exact=True).input_value() == "0.70",
    )
    check(
        "a waveform click moves playback position",
        abs(page.evaluate("document.getElementById('isolated-audio-preview').position") - 0.45) < 0.03,
    )
    page.mouse.move(bounds["x"] + bounds["width"] * 0.35, bounds["y"] + bounds["height"] / 2)
    page.mouse.down()
    page.mouse.move(bounds["x"] + bounds["width"] * 0.5, bounds["y"] + bounds["height"] / 2, steps=5)
    page.mouse.up()
    check(
        "a waveform drag seeks without trimming",
        abs(page.evaluate("document.getElementById('isolated-audio-preview').position") - 0.5) < 0.03
        and preview.get_by_role("spinbutton", name="Selection start", exact=True).input_value() == "0.20"
        and preview.get_by_role("spinbutton", name="Selection end", exact=True).input_value() == "0.70",
    )
    handle = preview.get_by_role("slider", name="Selection start handle", exact=True)
    handle_bounds = handle.bounding_box()
    page.mouse.move(
        handle_bounds["x"] + 7 + (handle_bounds["width"] - 14) * 0.2, handle_bounds["y"] + handle_bounds["height"] / 2
    )
    page.mouse.down()
    page.mouse.move(
        handle_bounds["x"] + 7 + (handle_bounds["width"] - 14) * 0.26,
        handle_bounds["y"] + handle_bounds["height"] / 2,
        steps=5,
    )
    page.mouse.up()
    check(
        "only a trim handle changes the selected boundary",
        float(preview.get_by_role("spinbutton", name="Selection start", exact=True).input_value()) > 0.2
        and abs(page.evaluate("document.getElementById('isolated-audio-preview').position") - 0.5) < 0.03,
    )
    set_range(preview, 0.2, 0.7)
    check(
        "the numeric fields keep the requested selection",
        preview.get_by_role("spinbutton", name="Selection start", exact=True).input_value() == "0.20"
        and preview.get_by_role("spinbutton", name="Selection end", exact=True).input_value() == "0.70",
    )
    with page.expect_download() as download:
        page.evaluate("void document.getElementById('isolated-audio-preview').action('download')")
    check(
        "the trimmed audio filename includes its range",
        "-0.2-0.7s-" in download.value.suggested_filename
        and download.value.suggested_filename.startswith("audio-morning-river-narration-"),
    )
    check("whole and trimmed exports have different names", whole_name != download.value.suggested_filename)
    with wave.open(str(download.value.path()), "rb") as audio:
        check("a selection download lasts half a second", audio.getnframes() == 12000 and audio.getframerate() == 24000)
        check(
            "a selection download preserves the exact source PCM",
            audio.readframes(audio.getnframes()) == samples[4800 * 2 : 16800 * 2],
        )
    page.evaluate("void document.getElementById('isolated-audio-preview').action('video')")
    page.wait_for_function("window.previewActions.length === 1")
    check(
        "Send to Video carries the selected range",
        page.evaluate(
            "window.previewActions[0].action === 'video' && window.previewActions[0].start === .2 && window.previewActions[0].end === .7 && window.previewActions[0].blob.size > 0"
        ),
    )
    page.evaluate("void document.getElementById('isolated-audio-preview').action('edit')")
    page.wait_for_function("window.previewActions.length === 2")
    check("Edit selection uses an explicit action", page.evaluate("window.previewActions[1].action === 'edit'"))
    cursor = preview.get_by_role("slider", name="Playback position", exact=True)
    cursor.focus()
    cursor.press("Home")
    cursor.press("ArrowRight")
    check(
        "the playback cursor supports the keyboard",
        page.evaluate("document.getElementById('isolated-audio-preview').position") > 0,
    )
    cursor.evaluate("input => { input.value = '.25'; input.dispatchEvent(new Event('input', {bubbles:true})); }")
    page.evaluate("document.getElementById('isolated-audio-preview').play()")
    page.wait_for_function("document.getElementById('isolated-audio-preview').playing")
    page.wait_for_function("document.getElementById('isolated-audio-preview').position > .27")
    preview.get_by_role("button", name="Pause", exact=True).click()
    paused_position = page.evaluate("document.getElementById('isolated-audio-preview').position")
    check("Pause keeps the playback cursor", 0.25 < paused_position < 0.7)
    preview.get_by_role("button", name="Play", exact=True).click()
    page.wait_for_function("document.getElementById('isolated-audio-preview').playing")
    check(
        "Play resumes from the paused cursor",
        page.evaluate("document.getElementById('isolated-audio-preview').position") >= paused_position,
    )
    cursor.evaluate("input => { input.value = '.6'; input.dispatchEvent(new Event('input', {bubbles:true})); }")
    check(
        "the cursor can seek during playback",
        page.evaluate("document.getElementById('isolated-audio-preview').position") >= 0.59,
    )
    page.wait_for_function("!document.getElementById('isolated-audio-preview').playing")
    check(
        "selection playback stops at its end and resets the cursor",
        abs(page.evaluate("document.getElementById('isolated-audio-preview').position") - 0.2) < 0.01,
    )
    check(
        "selection playback restores its action label",
        preview.get_by_role("button", name="Play", exact=True).is_visible(),
    )
    check(
        "the preview reports playback state changes",
        page.evaluate(
            "window.previewStates.some(state => state.playing) && window.previewStates.at(-1).playing === false"
        ),
    )
    handle = preview.get_by_role("slider", name="Selection start handle", exact=True)
    handle.focus()
    handle.press("ArrowRight")
    check(
        "the selection handles support the keyboard",
        float(preview.get_by_role("spinbutton", name="Selection start", exact=True).input_value()) > 0.2,
    )
    preview.get_by_role("spinbutton", name="Selection end", exact=True).fill("0")
    preview.get_by_role("spinbutton", name="Selection end", exact=True).press("Tab")
    check(
        "an invalid selection keeps a playable minimum range",
        page.evaluate(
            "document.getElementById('isolated-audio-preview').end - document.getElementById('isolated-audio-preview').start >= .199"
        ),
    )
    page.evaluate("document.getElementById('isolated-audio-preview').locked = true")
    page.evaluate(
        "async () => { await document.getElementById('isolated-audio-preview').action('video'); await document.getElementById('isolated-audio-preview').action('edit'); }"
    )
    check("a shared operation blocks handoff actions", page.evaluate("window.previewActions.length") == 2)
    with page.expect_download():
        page.evaluate("void document.getElementById('isolated-audio-preview').action('download')")
    check("a shared operation permits a download", True)
    page.evaluate("document.getElementById('isolated-audio-preview').locked = false")
    set_range(preview, 0.1, 0.6)
    held = []
    page.route("**/api/v1/audio/trim", lambda route: held.append(route))
    with page.expect_request("**/api/v1/audio/trim"):
        page.evaluate("void document.getElementById('isolated-audio-preview').action('video')")
    page.wait_for_function("document.getElementById('isolated-audio-preview').busy")
    check("a pending crop starts one trim request", len(held) == 1)
    page.evaluate(
        """encoded => {
      document.getElementById('isolated-audio-preview').blob = new Blob([Uint8Array.from(atob(encoded), letter => letter.charCodeAt(0))], {type:'audio/wav'});
    }""",
        base64.b64encode(second).decode(),
    )
    page.wait_for_function("Math.abs(document.getElementById('isolated-audio-preview').duration - 2) < 1 / 24000")
    for route in held:
        route.abort()
    page.unroute("**/api/v1/audio/trim")
    check(
        "a new take resets the selection",
        preview.get_by_role("spinbutton", name="Selection start", exact=True).input_value() == "0.00"
        and preview.get_by_role("spinbutton", name="Selection end", exact=True).input_value() == "2.00",
    )
    check("a stale crop cannot send the previous take", page.evaluate("window.previewActions.length") == 2)
    set_range(preview, 0.2, 0.8)
    page.route(
        "**/api/v1/audio/trim",
        lambda route: route.fulfill(status=400, json={"error": "The selection ends after the recording."}),
    )
    page.evaluate("void document.getElementById('isolated-audio-preview').action('video')")
    page.wait_for_function(
        "!document.getElementById('isolated-audio-preview').busy && Boolean(document.getElementById('isolated-audio-preview').error)"
    )
    check(
        "a failed crop shows the API error",
        "The selection ends after the recording." in preview.get_by_role("alert").inner_text(),
    )
    page.unroute("**/api/v1/audio/trim")
    page.set_viewport_size({"width": 390, "height": 700})
    bounds = preview.bounding_box()
    check("the preview fits a phone viewport", bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390)
    check("the preview has no horizontal overflow", preview.evaluate("node => node.scrollWidth <= node.clientWidth"))
    check("the browser reports no page errors", not errors)
    browser.close()
