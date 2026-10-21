"""Check Image and Video drafts against a fresh all-backend stub."""

import io
import sys
import wave

from PIL import Image
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]
image_buffer = io.BytesIO()
Image.new("RGB", (96, 64), "blue").save(image_buffer, format="PNG")
image_file = {"name": "draft.png", "mimeType": "image/png", "buffer": image_buffer.getvalue()}
audio_buffer = io.BytesIO()
with wave.open(audio_buffer, "wb") as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(16000)
    audio.writeframes(b"\x00\x00" * 16000)
audio_file = {"name": "draft.wav", "mimeType": "audio/wav", "buffer": audio_buffer.getvalue()}


def ready(page):
    page.wait_for_function("Boolean(formApi && run && kept && drafts && !drafts.loading())")
    page.wait_for_timeout(250)


def value(page, selector, setting):
    page.locator(selector).evaluate(
        "(input, setting) => { input.value = setting; input.dispatchEvent(new Event('input', {bubbles: true})); }",
        setting,
    )


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL)
    ready(page)
    page.fill("#prompt", "Keep the image draft")
    value(page, "#steps", "7")
    value(page, "#seed", "23")
    value(page, "#size", "768x512")
    page.locator("#reference").set_input_files(image_file)
    page.wait_for_function("references.length === 1")
    page.wait_for_timeout(150)
    page.reload()
    ready(page)
    assert page.input_value("#prompt") == "Keep the image draft"
    assert page.input_value("#steps") == "7"
    assert page.input_value("#seed") == "23"
    assert page.input_value("#size") == "768x512"
    assert page.evaluate("references.map(item => item.name)") == ["draft.png"]
    print("PASS Image refresh restores words, settings, and the uploaded reference", flush=True)
    page.locator('label[for="mode-edit"]').click()
    page.fill("#prompt", "Keep this edit instruction")
    page.locator("#reference").set_input_files(image_file)
    page.wait_for_function("references.length === 1")
    page.wait_for_timeout(150)
    page.reload()
    ready(page)
    assert page.locator("#mode-edit").is_checked()
    assert page.input_value("#prompt") == "Keep this edit instruction"
    assert page.evaluate("references.length") == 1
    print("PASS Image refresh restores Edit and its source", flush=True)

    page.locator("#reference").set_input_files(image_file)
    page.wait_for_function("references.length === 2")
    page.locator('label[for="each-each"]').click()
    page.locator("#each-rows textarea").nth(0).fill("Make the first one green")
    page.locator("#each-rows textarea").nth(1).fill("Make the second one red")
    page.evaluate("() => drafts.flushed()")
    page.reload()
    ready(page)
    assert page.locator("#each-each").is_checked()
    assert page.locator("#each-rows textarea").nth(0).input_value() == "Make the first one green"
    assert page.locator("#each-rows textarea").nth(1).input_value() == "Make the second one red"
    print("PASS Image refresh restores separate instructions for each reference", flush=True)

    page.locator("#media-video-mode").click()
    page.wait_for_function("mediaMode === 'video' && !workspaceSwitchPending")
    page.fill("#video-prompt", "Keep the video draft")
    value(page, "#video-seed", "37")
    value(page, "#video-duration", "49")
    page.locator("#video-media-upload").set_input_files(image_file)
    page.wait_for_function("videoStudio.imageReferences.length === 1")
    page.locator("#video-media-upload").set_input_files(audio_file)
    page.wait_for_function("Boolean(videoStudio.audio)")
    page.wait_for_timeout(150)
    page.reload()
    ready(page)
    assert page.evaluate("mediaMode") == "video"
    assert page.input_value("#video-prompt") == "Keep the video draft"
    assert page.input_value("#video-seed") == "37"
    assert page.input_value("#video-duration") == "49"
    assert page.evaluate("videoStudio.imageReferences.map(item => item.name)") == ["draft.png"]
    assert page.evaluate("videoStudio.audio.name") == "draft.wav"
    assert page.evaluate("videoStudio.audio.file.size") == len(audio_buffer.getvalue())
    print("PASS Video refresh restores its workspace, settings, image, and audio bytes", flush=True)

    page.locator('label[for="video-mode-edit"]').click()
    page.evaluate("""async () => {
      const canvas = document.createElement('canvas');
      canvas.width = 96; canvas.height = 64;
      const stream = canvas.captureStream(12);
      const recorder = new MediaRecorder(stream, {mimeType: 'video/webm'});
      const chunks = [];
      recorder.ondataavailable = event => chunks.push(event.data);
      const stopped = new Promise(resolve => { recorder.onstop = resolve; });
      recorder.start(); canvas.getContext('2d').fillRect(0, 0, 96, 64);
      await new Promise(resolve => setTimeout(resolve, 200));
      recorder.stop(); await stopped;
      stream.getTracks().forEach(track => track.stop());
      videoStudio.addVideoFiles([new File(chunks, 'edit-draft.webm', {type: 'video/webm'})]);
    }""")
    page.wait_for_function("Boolean(videoStudio.editTargetId)")
    page.wait_for_timeout(150)
    page.reload()
    ready(page)
    assert page.evaluate("videoMode") == "edit"
    assert page.evaluate("videoStudio.shownClips().map(clip => clip.name)") == ["edit-draft.webm"]
    assert page.evaluate("videoStudio.shownClips()[0].url.startsWith('blob:')")
    print("PASS Video refresh restores the uploaded edit clip with a fresh blob URL", flush=True)
    assert not errors, errors
    browser.close()
