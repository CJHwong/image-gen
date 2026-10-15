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
Image.new("RGB", (96, 64), (194, 89, 42)).save(REFERENCE)
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

    page.set_input_files("#reference", str(REFERENCE))
    page.get_by_role("img", name="reference.png").wait_for(state="visible", timeout=10000)
    page.get_by_role("button", name="Share references with Video").click()
    page.locator("#video-keyframe-track").wait_for(state="visible")
    check(
        "image references transfer to the video workspace",
        page.locator("#video-studio .video-reference").get_attribute("title") == "reference.png",
        page.locator("#video-studio .video-reference").get_attribute("title") or "no reference",
    )
    check(
        "video has no second image mode selector and shows a keyframe track",
        page.locator("#image-controls .modes").is_hidden()
        and page.locator("#video-controls .modes").count() == 0
        and page.locator("#video-keyframe-track [data-action='select-reference']").count() == 1,
    )
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
        "video files enter a separate gallery with a timeline",
        page.locator("#video-gallery .video-clip").count() == 1 and page.locator("#video-timeline").is_visible(),
        f"{page.locator('#video-gallery .video-clip').count()} clips",
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
    page.wait_for_function("() => document.querySelectorAll('#video-studio .video-reference').length === 2")
    check(
        "a video frame becomes a timed image keyframe",
        page.locator("#video-studio .video-reference input[type=number]").nth(1).input_value() != "0",
        page.locator("#video-studio .video-reference input[type=number]").nth(1).input_value(),
    )
    frame_index = int(page.locator("#video-studio .video-reference input[type=number]").nth(1).input_value())
    marker = page.locator("#video-keyframe-track [data-action='select-reference']").nth(1)
    marker_position = float(marker.evaluate("element => element.style.left.replace('%', '')"))
    check(
        "keyframe markers follow their output frame positions",
        page.locator("#video-keyframe-track [data-action='select-reference']").count() == 2
        and abs(marker_position - frame_index / 144 * 100) < 0.05
        and marker.get_attribute("aria-pressed") == "false",
        f"frame {frame_index} at {marker_position:.2f}%",
    )
    marker.click()
    check(
        "selecting a keyframe also selects its reference",
        marker.get_attribute("aria-pressed") == "true"
        and "selected" in (page.locator("#video-studio .video-reference").nth(1).get_attribute("class") or ""),
    )
    page.get_by_role("button", name="Use this frame in Image").click()
    page.get_by_role("button", name="Image", exact=True).wait_for(state="visible")
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
    page.get_by_role("button", name="Video", exact=True).wait_for(state="visible")
    check(
        "image and video galleries stay separate across handoff",
        page.locator("#strip-wrap").is_hidden()
        and page.locator("#video-gallery .video-clip").count() == 1
        and page.locator("#video-studio .video-reference").count() == 3,
        f"video references: {page.locator('#video-studio .video-reference').count()}, "
        f"names: {page.locator('#video-studio .video-reference').evaluate_all('nodes => nodes.map(node => node.title)')}, "
        f"state: {page.locator('#video-studio').evaluate('element => element.imageReferences.map(item => item.name)')}, "
        f"toast: {page.locator('#toasts').inner_text()}",
    )
    page.locator("#video-studio .video-reference input[type=number]").nth(1).fill("300")
    page.locator("#video-studio .video-reference input[type=number]").nth(1).dispatch_event("change")
    page.get_by_role("button", name="Generate video").click()
    page.wait_for_function(
        "() => document.querySelector('#video-request-status').textContent === 'Video generation failed.'",
        timeout=10000,
    )
    check(
        "keyframes outside the selected duration are stopped before the request",
        not video_posts
        and page.locator("#video-studio .video-error").inner_text() == "Keyframe frames must be between 0 and 144.",
        page.locator("#video-studio .video-error").inner_text(),
    )
    page.locator("#video-studio .video-reference input[type=number]").nth(1).fill("9")
    page.locator("#video-studio .video-reference input[type=number]").nth(1).dispatch_event("change")
    page.locator("#video-studio .video-reference input[type=range]").nth(1).evaluate(
        "element => { element.value = '0.55'; element.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.fill("#video-prompt", "A kite rises as the camera pans across the shore")
    page.select_option("#video-duration", "10")
    page.locator(".video-ratios button[data-ratio='9:16']").click()
    summary = page.locator("#video-frame-count").inner_text()
    check(
        "output details show derived dimensions, frames, and fixed frame rate",
        "544 × 960" in summary and "241 frames" in summary and "24 fps" in summary,  # noqa: RUF001
        summary,
    )
    check(
        "keyframe frame bounds follow the selected duration",
        page.locator("#video-studio .video-reference input[type=number]").nth(1).get_attribute("max") == "240",
        page.locator("#video-studio .video-reference input[type=number]").nth(1).get_attribute("max"),
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
        == int(page.locator("#video-studio .video-reference input[type=number]").nth(1).input_value())
        and request["references"][1].get("strength") == 0.55
        and all(len(reference.get("image", "")) > 100 for reference in request.get("references", [])),
        json.dumps({key: value for key, value in request.items() if key != "references"})
        + f", references: {len(request.get('references', []))}",
    )
    check(
        "stub video output enters the video gallery without fake media bytes",
        page.locator("#video-gallery .video-clip").count() == 2
        and page.get_by_text("The stub returns metadata only.").is_visible(),
        f"video clips: {page.locator('#video-gallery .video-clip').count()}",
    )

    page.get_by_role("button", name="Image", exact=True).click()
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
