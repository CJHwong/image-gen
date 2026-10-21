"""Check Voice batch identity, references, editing, storage races, and shared API results.

Run against a fresh `uv run studio --stub --all-backends --port <port>`.
"""

import io
import math
import struct
import sys
import time
import wave

from playwright.sync_api import sync_playwright
from voice_helpers import choose_voice_profile, create_voice_clips

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


def voice_page(context):
    page = context.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("document.getElementById('voice-studio').capabilities.modes.length === 3")
    page.wait_for_function("document.getElementById('media-voice-mode').getAttribute('aria-pressed') === 'true'")
    return page


def completed(request, operation_id):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        operation = request.get(URL + "/api/v1/operations/" + operation_id).json()
        if operation["status"] not in ("running", "stopping"):
            return operation
        time.sleep(0.1)
    raise AssertionError("The operation did not finish")


buffer = io.BytesIO()
with wave.open(buffer, "wb") as track:
    track.setnchannels(1)
    track.setsampwidth(2)
    # A non-native rate exercises pending decode, including the controlled race below.
    track.setframerate(48000)
    track.writeframes(
        b"".join(struct.pack("<h", int(4000 * math.sin(index * 2 * math.pi * 220 / 48000))) for index in range(96000))
    )

with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    errors = []
    owner = voice_page(context)
    owner.on("pageerror", lambda error: errors.append(str(error)))
    observer = voice_page(context)
    observer.on("pageerror", lambda error: errors.append(str(error)))
    choose_voice_profile(owner)
    create_voice_clips(owner, ["The same words.", "The same words."])
    check(
        "repeated whole scripts share their input",
        owner.evaluate("document.getElementById('voice-studio').segments.length") == 1,
    )
    observer.wait_for_function("document.getElementById('voice-studio').takesCount === 2", timeout=120000)
    check(
        "each repeated segment receives its own take",
        owner.get_by_role("button", name="Select audio 1", exact=True).count() == 1,
    )
    check(
        "the second repeated segment also receives a take",
        owner.get_by_role("button", name="Select audio 2", exact=True).count() == 1,
    )
    first_segment_id = owner.get_by_role("button", name="Select audio 1", exact=True).get_attribute("data-segment-id")
    check(
        "the waveform uses SVG elements",
        owner.locator(".audio-preview-wave svg rect").first.evaluate("line => line.namespaceURI")
        == "http://www.w3.org/2000/svg",
    )
    owner.evaluate("document.getElementById('voice-studio').saved")
    observer.evaluate("document.getElementById('voice-studio').saved")
    owner.reload()
    owner.wait_for_function("document.getElementById('voice-studio').takesCount === 2")
    check(
        "observer imports do not replace the saved script",
        owner.locator("#voice-text").input_value() == "",
    )

    owner.locator('label[for="voice-mode-clone"]').click()
    owner.locator("#voice-reference").set_input_files(
        {"name": "voice.wav", "mimeType": "audio/wav", "buffer": buffer.getvalue()}
    )
    owner.locator(".voice-reference-card").wait_for()
    check("a reference is normalized and displayed", "voice.wav" in owner.locator(".voice-reference-card").inner_text())
    check(
        "a loaded Voice reference uses the Video audio tray",
        owner.locator(".voice-reference-group .video-audios .video-audio").count() == 1,
    )
    check(
        "a loaded Voice reference uses the shared audio picture",
        owner.locator(".voice-reference-group .video-audio-picture .video-audio-badge").count() == 1,
    )
    picture = owner.locator(".voice-reference-group .video-audio-picture").bounding_box()
    check("the shared audio picture stays compact", picture["width"] == 60 and picture["height"] == 60)
    check(
        "the shared audio tile names the reference",
        owner.locator(".voice-reference-group .video-audio-name").inner_text() == "voice.wav",
    )
    check(
        "the shared audio tile uses the reference clear button",
        owner.locator(".voice-reference-group .video-audio-remove").get_attribute("aria-label")
        == "Clear voice reference",
    )
    check(
        "a selected reference has no Replace action",
        owner.get_by_role("button", name="Replace reference recording", exact=True).count() == 0,
    )
    check(
        "a selected reference disables recording", owner.get_by_role("button", name="Record", exact=True).is_disabled()
    )
    owner.get_by_role("button", name="Clear voice reference", exact=True).click()
    check(
        "clearing the reference enables recording", owner.get_by_role("button", name="Record", exact=True).is_enabled()
    )
    with owner.expect_file_chooser() as replacement:
        owner.get_by_role("button", name="Add reference recording", exact=True).click()
    check(
        "Add opens the reference chooser after clearing",
        replacement.value.element.get_attribute("id") == "voice-reference",
    )
    owner.evaluate("""() => {
      const original = AudioContext.prototype.decodeAudioData;
      AudioContext.prototype.decodeAudioData = async function(...args) {
        await new Promise(resolve => { window.finishReference = resolve; });
        AudioContext.prototype.decodeAudioData = original;
        return original.apply(this, args);
      };
    }""")
    replacement.value.set_files({"name": "replacement.wav", "mimeType": "audio/wav", "buffer": buffer.getvalue()})
    owner.wait_for_function("typeof window.finishReference === 'function'")
    check(
        "a pending reference cannot start a take with old audio",
        owner.locator("#voice-selected-reuse").is_disabled(),
    )
    owner.evaluate("window.finishReference()")
    owner.wait_for_function("document.getElementById('voice-studio').reference?.name === 'replacement.wav'")
    owner.get_by_role("button", name="Clear voice reference", exact=True).click()
    check("clearing a reference preserves generated takes", owner.locator(".voice-clip[data-take-id]").count() == 2)
    check("Clone without a reference cannot run", owner.locator("#voice-generate").is_disabled())
    owner.get_by_role("button", name="Select audio 1", exact=True).click()
    owner.locator("#voice-selected-edit").click()
    owner.locator("#voice-templates-toggle").click()
    owner.locator("#voice-templates").get_by_role("menuitem", name="Speed", exact=True).click()
    check(
        "Speed displays the same default it submits",
        owner.locator(".voice-template-field select").input_value() == "1.5",
    )
    check(
        "the edit caption describes one edited take",
        "Creates an edited clip" in owner.locator("#voice-go-sub").inner_text(),
    )
    with owner.expect_request(
        lambda request: request.url.endswith("/voice/operations") and request.method == "POST"
    ) as pending:
        owner.locator("#voice-generate").click()
    edit_payload = pending.value.post_data_json
    check(
        "edit templates reach the shared backend",
        edit_payload.get("template") == "Speed" and edit_payload.get("template_values", {}).get("speed") == "1.5",
    )
    owner.wait_for_function("document.getElementById('voice-studio').takesCount === 3", timeout=120000)
    check(
        "Speed adjusts the output length",
        abs(owner.evaluate("document.getElementById('voice-studio').segments[0].takes.at(-1).duration") - 0.67) < 0.02,
    )
    check(
        "editing adds a take to the selected segment",
        owner.locator(f'.voice-clip[data-segment-id="{first_segment_id}"]').count() == 3,
    )
    check(
        "editing preserves the script segments",
        owner.evaluate("document.getElementById('voice-studio').segments.length") == 1,
    )
    owner.evaluate("document.getElementById('voice-studio').saved")
    owner.reload()
    owner.wait_for_function("document.getElementById('voice-studio').takesCount === 3")
    check(
        "a new edit remains the selected take after reload",
        owner.get_by_role("button", name="Select audio 3", exact=True).get_attribute("aria-pressed") == "true",
    )
    owner.get_by_role("button", name="Select audio 1", exact=True).click()
    owner.get_by_role("button", name="Select audio 3", exact=True).click()
    owner.evaluate("document.getElementById('voice-studio').saved")
    owner.reload()
    owner.wait_for_function("document.getElementById('voice-studio').takesCount === 3")
    check(
        "selecting an alternate take persists",
        owner.get_by_role("button", name="Select audio 3", exact=True).get_attribute("aria-pressed") == "true",
    )
    owner.get_by_role("button", name="Select audio 1", exact=True).click()
    owner.evaluate("document.getElementById('voice-studio').saved")
    owner.reload()
    owner.wait_for_function("document.getElementById('voice-studio').takesCount === 3")
    check(
        "the selected take survives reload",
        owner.get_by_role("button", name="Select audio 1", exact=True).get_attribute("aria-pressed") == "true",
    )

    owner.evaluate("""() => {
      const voice = document.getElementById('voice-studio');
      voice.saved = new Promise(resolve => { window.releaseVoiceWrite = resolve; });
      voice.persist(true);
    }""")
    owner.locator("#theme-toggle").click()
    owner.get_by_role("menuitemcheckbox", name="Keep in this browser", exact=True).click()
    owner.evaluate("window.releaseVoiceWrite()")
    owner.evaluate("document.getElementById('voice-studio').saved")
    owner.wait_for_timeout(300)
    owner.reload()
    owner.wait_for_function("document.getElementById('voice-studio').loading === false")
    check(
        "Keep off prevents queued writes from restoring takes",
        owner.evaluate("document.getElementById('voice-studio').takesCount") == 0,
    )
    check("no browser errors occurred", not errors)
    browser.close()
