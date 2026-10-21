"""Check Voice recording and transport with deterministic PCM microphone input.

Run against a fresh `uv run studio --stub --all-backends --port <port>`.
"""

import sys

from playwright.sync_api import sync_playwright
from voice_helpers import synthetic_microphone

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


with sync_playwright() as tool:
    browser = tool.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
    context = browser.new_context(permissions=["microphone"], viewport={"width": 1440, "height": 1000})
    synthetic_microphone(context)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("document.getElementById('voice-studio').capabilities.modes.length === 3")
    page.locator('label[for="voice-mode-clone"]').click()
    page.evaluate("""() => {
      const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      navigator.mediaDevices.getUserMedia = async options => {
        await new Promise(resolve => { window.allowMicrophone = resolve; });
        const stream = await original(options);
        window.pendingStream = stream;
        return stream;
      };
      document.getElementById('voice-studio').toggleRecording();
      window.originalMicrophone = original;
    }""")
    page.locator('label[for="voice-mode-design"]').click()
    page.evaluate("window.allowMicrophone()")
    page.wait_for_function("!document.getElementById('voice-studio').recordingPending")
    check(
        "Design cancels a pending microphone request",
        page.evaluate("window.pendingStream.getTracks().every(track => track.readyState === 'ended')"),
    )
    page.evaluate("() => { navigator.mediaDevices.getUserMedia = window.originalMicrophone; }")
    page.locator('label[for="voice-mode-clone"]').click()
    page.evaluate("""() => {
      const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      window.microphoneCalls = 0;
      navigator.mediaDevices.getUserMedia = async options => {
        window.microphoneCalls++;
        await new Promise(resolve => setTimeout(resolve, 300));
        const stream = await original(options);
        window.recordingStream = stream;
        return stream;
      };
      const voice = document.getElementById('voice-studio');
      voice.toggleRecording();
      voice.toggleRecording();
    }""")
    page.wait_for_function("document.getElementById('voice-studio').recording")
    check("repeated presses acquire only one microphone stream", page.evaluate("window.microphoneCalls") == 1)
    page.wait_for_timeout(600)
    page.locator('label[for="voice-mode-design"]').click()
    page.wait_for_function("window.recordingStream.getTracks().every(track => track.readyState === 'ended')")
    check("Design stops an active microphone recording", True)
    page.locator('label[for="voice-mode-clone"]').click()
    page.locator(".voice-reference-card").wait_for()
    page.get_by_role("button", name="Clear voice reference", exact=True).click()
    check(
        "clearing the stopped recording enables Record",
        page.get_by_role("button", name="Record", exact=True).is_enabled(),
    )
    page.evaluate("document.getElementById('voice-studio').toggleRecording()")
    page.wait_for_function("document.getElementById('voice-studio').recording")
    page.wait_for_timeout(600)
    page.get_by_role("button", name="Image", exact=True).click()
    page.wait_for_function("window.recordingStream.getTracks().every(track => track.readyState === 'ended')")
    check("leaving Voice stops microphone tracks", True)
    page.get_by_role("button", name="Voice", exact=True).click()
    page.locator(".voice-reference-card").wait_for()
    check(
        "the stopped recording becomes a reference",
        "recording.webm" in page.locator(".voice-reference-card").inner_text(),
    )
    check(
        "the recorded reference has no Replace action",
        page.get_by_role("button", name="Replace reference recording", exact=True).count() == 0,
    )
    check("a recorded reference disables Record", page.get_by_role("button", name="Record", exact=True).is_disabled())
    page.locator("#voice-text").fill("This is a transport test.")
    page.locator("#voice-generate").click()
    page.wait_for_function("document.getElementById('voice-studio').takesCount === 1", timeout=120000)
    preview = page.locator("#voice-audio-preview")
    preview.get_by_role("button", name="Play", exact=True).click()
    page.wait_for_function("document.getElementById('voice-audio-preview').position > .1")
    preview.get_by_role("button", name="Pause", exact=True).click()
    paused = page.evaluate("document.getElementById('voice-audio-preview').position")
    preview.get_by_role("button", name="Play", exact=True).click()
    page.wait_for_function("value => document.getElementById('voice-audio-preview').position > value", arg=paused)
    check("Play resumes a paused clip", True)
    preview.get_by_role("button", name="Pause", exact=True).click()
    preview.get_by_role("slider", name="Playback position", exact=True).evaluate(
        "input => { input.value = '0.2'; input.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    check(
        "the playhead seeks within the audio",
        page.evaluate("document.getElementById('voice-audio-preview').position") > 0.15,
    )
    check(
        "a successful generation restores Add reference",
        page.get_by_role("button", name="Add reference recording", exact=True).is_visible(),
    )
    check("a successful generation enables Record", page.get_by_role("button", name="Record", exact=True).is_enabled())
    page.evaluate("""() => {
      const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      navigator.mediaDevices.getUserMedia = async options => {
        await new Promise(resolve => { window.finishMicrophone = resolve; });
        return original(options);
      };
      document.getElementById('voice-studio').toggleRecording();
    }""")
    check(
        "a pending microphone cannot start a take with old audio",
        page.locator("#voice-selected-reuse").is_disabled(),
    )
    check(
        "a pending microphone cannot replace the Clone reference", page.locator("#voice-selected-clone").is_disabled()
    )
    page.locator('label[for="voice-mode-design"]').click()
    page.evaluate("window.finishMicrophone()")
    page.wait_for_function("!document.getElementById('voice-studio').recordingPending")
    check("no browser errors occurred", not errors)
    browser.close()
