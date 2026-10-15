"""Check image and video handoffs against the local stub server.

uv run studio --stub --port <port>
uv run --with playwright python tests/e2e/verify_media_studio.py <port>
"""

import json
import shutil
import sys
import tempfile
import urllib.parse
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

PORT = sys.argv[1]
URL = f"http://127.0.0.1:{PORT}/"
SCRATCH = Path(tempfile.mkdtemp(prefix="verify-media-studio-"))
REFERENCE = SCRATCH / "reference.png"
Image.new("RGB", (1024, 1024), (194, 89, 42)).save(REFERENCE)
results = []


def check(name, passed, detail=""):
    results.append((name, passed))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def make_video(page):
    values = page.evaluate(
        """async () => {
          const canvas = document.createElement('canvas');
          canvas.width = 96;
          canvas.height = 64;
          const context = canvas.getContext('2d');
          const stream = canvas.captureStream(12);
          const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp8')
            ? 'video/webm;codecs=vp8' : 'video/webm';
          const recorder = new MediaRecorder(stream, {mimeType: mime});
          const chunks = [];
          recorder.addEventListener('dataavailable', event => chunks.push(event.data));
          const stopped = new Promise(resolve => recorder.addEventListener('stop', resolve, {once: true}));
          recorder.start();
          for (let frame = 0; frame < 12; frame += 1) {
            context.fillStyle = frame < 6 ? '#c2562a' : '#3779a8';
            context.fillRect(0, 0, canvas.width, canvas.height);
            await new Promise(resolve => setTimeout(resolve, 70));
          }
          recorder.stop();
          await stopped;
          stream.getTracks().forEach(track => track.stop());
          return Array.from(new Uint8Array(await new Blob(chunks, {type: mime}).arrayBuffer()));
        }"""
    )
    return bytes(values)


def post_values(request):
    return urllib.parse.parse_qs(request.post_data or "", keep_blank_values=True)


def paste_file(page, content, name, mime_type):
    return page.evaluate(
        """({fileBytes, name, mimeType}) => {
          const transfer = new DataTransfer();
          transfer.items.add(new File([new Uint8Array(fileBytes)], name, {type: mimeType}));
          const event = new ClipboardEvent('paste', {
            bubbles: true,
            cancelable: true,
            clipboardData: transfer,
          });
          document.dispatchEvent(event);
          return event.defaultPrevented;
        }""",
        {"fileBytes": list(content), "name": name, "mimeType": mime_type},
    )


def switch_workspace(page, workspace):
    page.locator(f"#media-{workspace}-mode").click()
    page.wait_for_function(
        "workspace => document.getElementById('media-' + workspace + '-mode').getAttribute('aria-pressed') === 'true'",
        arg=workspace,
        timeout=10000,
    )


def drop_file(page, content, name, mime_type):
    return page.evaluate(
        """({fileBytes, name, mimeType}) => {
          const panel = document.getElementById('video-source-panel');
          const transfer = new DataTransfer();
          transfer.items.add(new File([new Uint8Array(fileBytes)], name, {type: mimeType}));
          const over = new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: transfer});
          panel.dispatchEvent(over);
          const highlighted = panel.classList.contains('drop-over');
          const drop = new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: transfer});
          panel.dispatchEvent(drop);
          return {overPrevented: over.defaultPrevented, dropPrevented: drop.defaultPrevented,
            highlighted: highlighted, cleared: !panel.classList.contains('drop-over')};
        }""",
        {"fileBytes": list(content), "name": name, "mimeType": mime_type},
    )


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    posts = []
    video_posts = []
    page.on("pageerror", lambda error: errors.append(error.stack or str(error)))
    page.on(
        "request",
        lambda request: (
            posts.append(post_values(request))
            if request.method == "POST" and request.url.endswith("/generate")
            else None
        ),
    )
    page.on(
        "request",
        lambda request: (
            video_posts.append(json.loads(request.post_data or "{}"))
            if request.method == "POST" and request.url.endswith("/video/generate")
            else None
        ),
    )
    page.goto(URL)
    page.locator("#go[data-state='idle']").wait_for(state="visible", timeout=60000)
    check(
        "workspace navigation sits above the image-specific modes",
        page.locator(".topbar #workspace-tabs").count() == 1
        and page.locator("#form #workspace-tabs").count() == 0
        and page.locator("#image-controls .modes").is_visible(),
    )
    page.route(
        "**/workspace",
        lambda route: route.fulfill(status=409, content_type="text/plain", body="Wait for the run to end."),
    )
    page.locator("#media-video-mode").click()
    page.wait_for_function("() => document.querySelector('#toasts').textContent.includes('Wait for the run to end.')")
    check(
        "a blocked workspace switch keeps the active workspace visible",
        page.locator("#media-image-mode").get_attribute("aria-pressed") == "true"
        and page.locator("#media-video-mode").get_attribute("aria-pressed") == "false"
        and page.locator("#image-stage").is_visible()
        and page.locator("#video-studio").is_hidden(),
        page.locator("#toasts").inner_text(),
    )
    page.unroute("**/workspace")
    switch_workspace(page, "image")
    page.click("#backend-toggle")
    image_models = page.get_by_role("menuitemradio").all_text_contents()
    page.keyboard.press("Escape")
    check(
        "Image mode lists image models in its selector",
        len(image_models) == 3 and "Qwen-Image-2.1-Turbo" in image_models[0],
        ", ".join(image_models),
    )

    page.fill("#prompt", "A copper cup on a wooden table")
    page.dispatch_event("#prompt", "input")
    check(
        "Turbo text generation shows its measured time estimate",
        page.locator("#go-sub").inner_text() == "about 35s",
        page.locator("#go-sub").inner_text(),
    )
    paste_prevented = paste_file(page, REFERENCE.read_bytes(), "reference.png", "image/png")
    page.get_by_role("img", name="reference.png").wait_for(state="visible", timeout=10000)
    check(
        "pasted images become image-mode references",
        paste_prevented and page.locator("#thumbs img").count() == 1,
    )
    check(
        "Turbo reference generation shows its measured time estimate",
        page.locator("#go-sub").inner_text() == "about 25s",
        page.locator("#go-sub").inner_text(),
    )
    page.locator("#strength").evaluate(
        "element => { element.value = '0.8'; element.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    check(
        "Turbo reference estimate follows image strength",
        page.locator("#go-sub").inner_text() == "about 10s",
        page.locator("#go-sub").inner_text(),
    )
    page.locator("#strength").evaluate(
        "element => { element.value = '0.4'; element.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.get_by_role("button", name="Share references with Video").click()
    page.wait_for_function("() => document.querySelector('#media-video-mode').getAttribute('aria-pressed') === 'true'")
    page.locator("#video-keyframe-track").wait_for(state="visible")
    check(
        "image references transfer to the video workspace",
        page.locator("#video-source-panel .video-reference").get_attribute("title") == "reference.png",
        page.locator("#video-source-panel .video-reference").get_attribute("title") or "no reference",
    )
    check(
        "Video mode shows its own selected model",
        page.locator("#backend-toggle .name").inner_text() == "LTX-2.5"
        and page.locator(".dial .badge").inner_text() == "24 fps"
        and page.locator("#backend-toggle").is_disabled(),
        page.locator("#backend-toggle").inner_text().replace("\n", " "),
    )
    check(
        "video has no second image mode selector and shows a keyframe track",
        page.locator("#image-controls .modes").is_hidden()
        and page.locator("#video-controls .modes").count() == 0
        and page.locator("#video-keyframe-track [data-action='select-reference']").count() == 1,
    )
    check(
        "video sources stay beside the prompt in the right sidebar",
        page.locator("aside #video-source-panel").count() == 1
        and page.locator(".work #video-source-panel").count() == 0
        and page.locator("#video-timeline").is_visible(),
    )
    paste_prevented = paste_file(page, REFERENCE.read_bytes(), "clipboard.png", "image/png")
    page.wait_for_function("() => document.querySelectorAll('#video-source-panel .video-reference').length === 2")
    check(
        "pasted images enter video references without changing image references",
        paste_prevented
        and page.locator("#video-source-panel .video-reference").count() == 2
        and page.locator("#thumbs img").count() == 1
        and page.locator("#video-source-panel .video-reference").nth(1).get_attribute("title") == "clipboard.png",
    )
    page.get_by_role("button", name="Remove video reference clipboard.png").click()
    page.wait_for_function("() => document.querySelectorAll('#video-source-panel .video-reference').length === 1")
    drop_result = drop_file(page, REFERENCE.read_bytes(), "dropped.png", "image/png")
    page.wait_for_function("() => document.querySelectorAll('#video-source-panel .video-reference').length === 2")
    check(
        "dropped images enter the source panel and clear its drop highlight",
        drop_result == {"overPrevented": True, "dropPrevented": True, "highlighted": True, "cleared": True}
        and page.locator("#video-source-panel .video-reference").nth(1).get_attribute("title") == "dropped.png",
        str(drop_result),
    )
    page.get_by_role("button", name="Remove video reference dropped.png").click()
    page.wait_for_function("() => document.querySelectorAll('#video-source-panel .video-reference').length === 1")
    switch_workspace(page, "image")
    check(
        "returning to Image restores its separate model choice",
        page.locator("#backend-toggle .name").inner_text() == "Qwen-Image-2.1-Turbo",
        page.locator("#backend-toggle .name").inner_text(),
    )
    page.locator("label[for=mode-edit]").click()
    page.set_input_files("#reference", str(REFERENCE))
    page.get_by_role("img", name="reference.png").wait_for(state="visible", timeout=10000)
    page.fill("#prompt", "Replace the copper cup with a glass vase")
    page.dispatch_event("#prompt", "input")
    page.wait_for_function("() => document.querySelector('#go-sub').textContent.includes('about')")
    check(
        "Turbo edit shows its measured time estimate",
        page.locator("#go-sub").inner_text() == "about 55s",
        page.locator("#go-sub").inner_text(),
    )
    page.locator("label[for=mode-generate]").click()
    switch_workspace(page, "video")
    check(
        "video duration starts at the documented 121-frame example",
        page.locator("#video-duration").input_value() == "121"
        and "5.04 seconds" in page.locator("#video-frame-count").inner_text(),
        page.locator("#video-frame-count").inner_text(),
    )
    page.get_by_role("button", name="Set duration to 15 seconds").click()
    check(
        "15-second preset reaches the 361-frame cap",
        page.locator("#video-duration").input_value() == "361"
        and "361 frames" in page.locator("#video-frame-count").inner_text(),
    )
    page.get_by_role("button", name="Set duration to 5 seconds").click()
    page.locator("#video-image-upload").set_input_files(
        {"name": "notes.txt", "mimeType": "text/plain", "buffer": b"not an image"}
    )
    page.locator("#video-studio .video-error").wait_for(state="visible", timeout=10000)
    check(
        "invalid still-image uploads show a visible error",
        page.locator("#video-studio .video-error").inner_text() == "Choose an image file.",
        page.locator("#video-studio .video-error").inner_text(),
    )

    video_bytes = make_video(page)
    paste_prevented = paste_file(page, video_bytes, "clipboard.webm", "video/webm")
    page.wait_for_function("() => document.querySelectorAll('#video-source-list .video-source').length === 1")
    check(
        "pasted video files enter source assets, not the output gallery",
        paste_prevented
        and page.locator("#video-gallery .video-clip").count() == 0
        and page.locator("#video-source-list .video-source").count() == 1,
    )
    page.get_by_role("button", name="Remove source video clipboard.webm").click()
    page.locator("#video-upload").set_input_files(
        {"name": "demo.webm", "mimeType": "video/webm", "buffer": video_bytes}
    )
    page.wait_for_function(
        "() => { const video = document.querySelector('#video-preview');"
        "return video && video.readyState >= 2 && video.videoWidth > 0"
        " && Number.isFinite(video.duration) && video.duration > 0; }",
        timeout=30000,
    )
    check(
        "imported video files stay in source assets with a timeline",
        page.locator("#video-source-list .video-source").count() == 1
        and page.locator("#video-gallery .video-clip").count() == 0
        and page.locator("#video-timeline").is_visible(),
        f"{page.locator('#video-source-list .video-source').count()} sources",
    )

    page.locator("#video-playhead").evaluate(
        "element => { element.value = String(Math.min(0.4, Number(element.max) / 2));"
        "element.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.wait_for_function(
        "() => { const video = document.querySelector('#video-preview');"
        "return video && video.currentTime > 0.1 && video.readyState >= 2; }",
        timeout=10000,
    )
    playhead_position = page.locator(".source-track").evaluate(
        "element => element.style.getPropertyValue('--playhead')"
    )
    check(
        "timeline playhead follows the selected frame time",
        bool(playhead_position) and float(playhead_position.rstrip("%")) > 0,
        playhead_position or "no playhead position",
    )
    page.get_by_role("button", name="Add frame to Video").click()
    page.wait_for_function("() => document.querySelectorAll('#video-source-panel .video-reference').length === 2")
    check(
        "a video frame becomes a timed image keyframe",
        page.locator("#video-source-panel .video-reference input[type=number]").nth(1).input_value() != "0",
        page.locator("#video-source-panel .video-reference input[type=number]").nth(1).input_value(),
    )
    frame_index = int(page.locator("#video-source-panel .video-reference input[type=number]").nth(1).input_value())
    marker = page.locator("#video-keyframe-track [data-action='select-reference']").nth(1)
    marker_position = float(marker.evaluate("element => element.style.left.replace('%', '')"))
    check(
        "keyframe markers follow their output frame positions",
        page.locator("#video-keyframe-track [data-action='select-reference']").count() == 2
        and abs(marker_position - frame_index / 120 * 100) < 0.05
        and marker.get_attribute("aria-pressed") == "false",
        f"frame {frame_index} at {marker_position:.2f}%",
    )
    marker.click()
    check(
        "selecting a keyframe also selects its reference",
        marker.get_attribute("aria-pressed") == "true"
        and "selected" in (page.locator("#video-source-panel .video-reference").nth(1).get_attribute("class") or ""),
    )
    page.get_by_role("button", name="Use this frame in Image").click()
    page.wait_for_function("() => document.querySelector('#media-image-mode').getAttribute('aria-pressed') === 'true'")
    page.locator("#thumbs img[alt^='demo.webm frame']").wait_for(state="visible", timeout=10000)
    check(
        "a video timeline frame becomes an image reference",
        page.locator("#thumbs img").count() == 1
        and page.locator("#thumbs img").first.get_attribute("alt").startswith("demo.webm frame"),
        page.locator("#thumbs img").first.get_attribute("alt") or "no image reference",
    )

    page.fill("#prompt", "a copper cup on a table")
    page.dispatch_event("#prompt", "input")
    page.locator("#steps").evaluate(
        "element => { element.value = '8'; element.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.click("#go")
    page.locator("#go[data-state='busy']").wait_for(state="visible", timeout=30000)
    page.locator("#go[data-state='idle']").wait_for(state="visible", timeout=600000)
    sent = json.loads(posts[-1]["references"][0]) if posts else []
    check(
        "the image run receives the captured PNG reference",
        len(sent) == 1 and len(sent[0]) > 100,
        f"{len(sent)} references",
    )

    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Use in Video").click()
    page.wait_for_function("() => document.querySelector('#media-video-mode').getAttribute('aria-pressed') === 'true'")
    page.get_by_role("button", name="Video", exact=True).wait_for(state="visible")
    check(
        "image and video galleries stay separate across handoff",
        page.locator("#strip-wrap").is_hidden()
        and page.locator("#media-video-mode").get_attribute("aria-pressed") == "true"
        and page.locator("#video-gallery .video-clip").count() == 0
        and page.locator("#video-source-list .video-source").count() == 1
        and page.locator("#video-source-panel .video-reference").count() == 3,
        f"video mode: {page.locator('#media-video-mode').get_attribute('aria-pressed')}, "
        f"strip hidden: {page.locator('#strip-wrap').is_hidden()}, "
        f"output clips: {page.locator('#video-gallery .video-clip').count()}, "
        f"video references: {page.locator('#video-source-panel .video-reference').count()}, "
        f"names: {page.locator('#video-source-panel .video-reference').evaluate_all('nodes => nodes.map(node => node.title)')}, "
        f"state: {page.locator('#video-studio').evaluate('element => element.imageReferences.map(item => item.name)')}, "
        f"toast: {page.locator('#toasts').inner_text()}",
    )
    page.locator("#video-source-panel .video-reference input[type=number]").nth(1).fill("300")
    page.locator("#video-source-panel .video-reference input[type=number]").nth(1).dispatch_event("change")
    page.get_by_role("button", name="Generate video").click()
    page.wait_for_function(
        "() => document.querySelector('#video-request-status').textContent === 'Video generation failed.'",
        timeout=10000,
    )
    check(
        "keyframes outside the selected duration are stopped before the request",
        not video_posts
        and page.locator("#video-studio .video-error").inner_text() == "Keyframe frames must be between 0 and 120.",
        page.locator("#video-studio .video-error").inner_text(),
    )
    page.locator("#video-source-panel .video-reference input[type=number]").nth(1).fill("9")
    page.locator("#video-source-panel .video-reference input[type=number]").nth(1).dispatch_event("change")
    page.locator("#video-source-panel .video-reference input[type=range]").nth(1).evaluate(
        "element => { element.value = '0.55'; element.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.fill("#video-prompt", "A kite rises as the camera pans across the shore")
    page.get_by_role("button", name="Set duration to 15 seconds").click()
    check(
        "duration preset selects the 361-frame maximum",
        page.locator("#video-duration").input_value() == "361"
        and "361 frames" in page.locator("#video-frame-count").inner_text(),
    )
    page.get_by_role("button", name="Set duration to 10 seconds").click()
    page.locator(".video-ratios button[data-ratio='9:16']").click()
    summary = page.locator("#video-frame-count").inner_text()
    check(
        "duration follows the frame grid and shows derived output settings",
        page.locator("#video-duration").input_value() == "241"
        and "10.04 seconds" in summary
        and "544 × 960" in summary  # noqa: RUF001
        and "241 frames" in summary
        and "24 fps" in summary,
        summary,
    )
    check(
        "keyframe frame bounds follow the selected duration",
        page.locator("#video-source-panel .video-reference input[type=number]").nth(1).get_attribute("max") == "240",
        page.locator("#video-source-panel .video-reference input[type=number]").nth(1).get_attribute("max"),
    )
    page.locator("#video-advanced summary").click()
    page.fill("#video-seed", "4294967296")
    page.get_by_role("button", name="Generate video").click()
    page.wait_for_function(
        "() => document.querySelector('#video-request-status').textContent === 'Video generation failed.'",
        timeout=10000,
    )
    check(
        "out-of-range video seeds are stopped before the request",
        len(video_posts) == 0
        and page.locator("#video-studio .video-error").inner_text()
        == "Seed must be a whole number from 0 to 4294967295.",
        page.locator("#video-studio .video-error").inner_text(),
    )
    page.fill("#video-seed", "42")
    page.get_by_role("button", name="Generate video").click()
    page.wait_for_function(
        "() => ['Stub response added. No video file was generated.', 'Video generation failed.']"
        ".includes(document.querySelector('#video-request-status').textContent)",
        timeout=30000,
    )
    request_status = page.locator("#video-request-status").inner_text()
    check(
        "stub video generation completes without a media file",
        request_status == "Stub response added. No video file was generated.",
        request_status + ": " + page.locator("#video-studio .video-error").inner_text()
        if page.locator("#video-studio .video-error").count()
        else request_status,
    )
    request = video_posts[-1] if video_posts else {}
    check(
        "video generation sends selected settings and shared keyframes",
        request.get("num_frames") == 241
        and request.get("width") == 544
        and request.get("height") == 960
        and len(request.get("references", [])) == 3
        and request.get("seed") == 42
        and request["references"][1].get("frame_index")
        == int(page.locator("#video-source-panel .video-reference input[type=number]").nth(1).input_value())
        and request["references"][1].get("strength") == 0.55
        and all(len(reference.get("image", "")) > 100 for reference in request.get("references", [])),
        json.dumps({key: value for key, value in request.items() if key != "references"})
        + f", references: {len(request.get('references', []))}",
    )
    check(
        "stub video output enters the video gallery without fake media bytes",
        page.locator("#video-gallery .video-clip").count() == 1
        and page.locator("#video-source-list .video-source").count() == 1
        and page.get_by_text("The stub returns metadata only.").is_visible(),
        f"video clips: {page.locator('#video-gallery .video-clip').count()}",
    )
    switch_workspace(page, "image")
    check(
        "the image gallery returns with its generated result",
        page.locator("#strip-wrap").is_visible()
        and page.locator("#strip .frame").count() == 1
        and page.locator("#video-studio").is_hidden(),
        f"image frames: {page.locator('#strip .frame').count()}",
    )
    check("the browser reports no page errors", not errors, str(errors))
    browser.close()

shutil.rmtree(SCRATCH, ignore_errors=True)
failed = [name for name, passed in results if not passed]
print(f"\n{len(results) - len(failed)}/{len(results)} passed", "FAILED: " + ", ".join(failed) if failed else "")
sys.exit(1 if failed else 0)
