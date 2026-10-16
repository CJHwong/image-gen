"""Check image and video handoffs against the local stub server.

uv run studio --stub --port <port>
uv run --with playwright python tests/e2e/verify_media_studio.py <port>
"""

import json
import re
import shutil
import sys
import tempfile
import urllib.parse
from pathlib import Path

from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
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


def paste_shortcut_file(page, content, name, mime_type):
    return page.evaluate(
        """({fileBytes, name, mimeType}) => {
          const blob = new Blob([new Uint8Array(fileBytes)], {type: mimeType});
          const item = {name, types: [mimeType], getType: async () => blob};
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {read: async () => [item]},
          });
          const event = new KeyboardEvent('keydown', {
            key: 'p', metaKey: true, bubbles: true, cancelable: true,
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
    console_errors = []
    posts = []
    video_posts = []
    page.on("pageerror", lambda error: errors.append(error.stack or str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
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
    stable_switch = page.evaluate(
        """() => {
          const name = document.querySelector('#backend-toggle .name');
          const tabs = document.querySelector('#workspace-tabs');
          const before = tabs.getBoundingClientRect().left + tabs.getBoundingClientRect().width / 2;
          const saved = name.textContent;
          name.textContent = 'A deliberately very long image model name '.repeat(8);
          const after = tabs.getBoundingClientRect().left + tabs.getBoundingClientRect().width / 2;
          const clipped = name.scrollWidth > name.clientWidth;
          renderBackendSelector();
          return {before, after, clipped};
        }"""
    )
    check(
        "Image and Video stay centered when the model name changes width",
        abs(stable_switch["after"] - stable_switch["before"]) < 1 and stable_switch["clipped"],
        str(stable_switch),
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
    page.locator("#video-reference-track").wait_for(state="visible")
    check(
        "image references transfer to the video workspace",
        page.locator("#video-source-panel .video-reference").get_attribute("title") == "reference.png",
        page.locator("#video-source-panel .video-reference").get_attribute("title") or "no reference",
    )
    reference_options = page.locator("#video-source-panel .video-reference-options").first
    check(
        "reference influence stays out of the default controls",
        reference_options.count() == 1
        and reference_options.evaluate("element => !element.open")
        and page.locator("#video-source-panel [data-action='reference-frame']").count() == 0,
        "keyframe timing stays on the timeline",
    )
    if reference_options.count():
        reference_options.locator("summary").click()
    reference_options_open = reference_options.count() and reference_options.evaluate("element => element.open")
    check(
        "reference options explain the influence control",
        reference_options_open
        and "Reference influence" in reference_options.inner_text()
        and "Adjust only when an image needs more or less influence." in reference_options.inner_text(),
        reference_options.inner_text() if reference_options.count() else "missing options",
    )
    if reference_options.count() and reference_options.evaluate("element => element.open"):
        reference_options.locator("summary").click()
    check(
        "Video mode shows its own selected model",
        page.locator("#backend-toggle .name").inner_text() == "LTX-2.5"
        and page.locator(".dial .badge").inner_text() == "24 fps"
        and page.locator("#backend-toggle").is_disabled(),
        page.locator("#backend-toggle").inner_text().replace("\n", " "),
    )
    check(
        "Video uses the shared Prompt label",
        page.locator("#video-controls label[for='video-prompt']").inner_text() == "Prompt"
        and page.locator("#video-controls").get_by_text("Video prompt", exact=True).count() == 0,
        page.locator("#video-controls .prompt-field").inner_text(),
    )
    video_switch_position = page.evaluate(
        """() => {
          const name = document.querySelector('#backend-toggle .name');
          const tabs = document.querySelector('#workspace-tabs');
          const before = tabs.getBoundingClientRect().left + tabs.getBoundingClientRect().width / 2;
          const saved = name.textContent;
          name.textContent = 'LTX-2.5 with a much longer display name';
          const after = tabs.getBoundingClientRect().left + tabs.getBoundingClientRect().width / 2;
          name.textContent = saved;
          return {before, after};
        }"""
    )
    check(
        "video model name changes do not move the workspace switch",
        abs(video_switch_position["after"] - video_switch_position["before"]) < 1,
        str(video_switch_position),
    )
    model_settings = page.evaluate(
        """() => {
          const capabilities = STUDIO.video.capabilities;
          const original = {
            durationPresets: capabilities.duration_presets,
            defaultFrames: capabilities.default_frames,
            shapes: capabilities.shapes,
            defaultShapeRatio: capabilities.default_shape_ratio,
            maxReferences: capabilities.max_references,
            minReferenceStrength: capabilities.min_reference_strength,
            maxReferenceStrength: capabilities.max_reference_strength,
            referenceStrengthStep: capabilities.reference_strength_step,
            defaultReferenceStrength: capabilities.default_reference_strength,
            minSeed: capabilities.min_seed,
            maxSeed: capabilities.max_seed,
          };
          capabilities.duration_presets = [49, 97, 145];
          capabilities.default_frames = 97;
          capabilities.shapes = [
            {ratio: '5:4', width: 640, height: 512},
            {ratio: '4:5', width: 512, height: 640},
          ];
          capabilities.default_shape_ratio = '4:5';
          capabilities.max_references = 2;
          capabilities.min_reference_strength = 0.2;
          capabilities.max_reference_strength = 0.8;
          capabilities.reference_strength_step = 0.2;
          capabilities.default_reference_strength = 0.4;
          capabilities.min_seed = 17;
          capabilities.max_seed = 99;
          applyVideoCapabilities();
          videoStudio.setModelCapabilities(capabilities);
          const reference = {
            id: 'model-limit-one',
            name: 'model-limit.png',
            src: 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=',
            base64: 'R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=',
            frameIndex: 0,
            strength: 0.4,
          };
          videoStudio.addImageReference(reference);
          videoStudio.addImageReference({...reference, id: 'model-limit-two'});
          const referenceLimitError = videoStudio.error;
          const referenceStrengths = document.querySelectorAll(
            '#video-source-panel .video-reference-options input[type=range]'
          );
          const referenceOptions = document.querySelector('.video-reference-options');
          const defaultReferenceStrength = referenceStrengths[1]?.value ?? null;
          videoStudio.removeImageReference(reference.id);
          videoStudio.clearError();
          const state = {
            durationRange: [
              document.querySelector('#video-duration').min,
              document.querySelector('#video-duration').max,
              document.querySelector('#video-duration').step,
              document.querySelector('#video-duration').value,
            ],
            durations: [...document.querySelectorAll('[data-duration-frames]')].map(button => ({
              frames: button.dataset.durationFrames,
              label: button.textContent,
              selected: button.getAttribute('aria-pressed'),
            })),
            shapes: [...document.querySelectorAll('.video-ratios button')].map(button => ({
              ratio: button.dataset.ratio,
              width: button.dataset.width,
              height: button.dataset.height,
              selected: button.getAttribute('aria-pressed'),
            })),
            defaultShape: document.querySelector('#video-frame-count').textContent,
            referenceLimit: videoStudio.maxReferences,
            referenceLimitError: referenceLimitError,
            defaultReferenceStrength: defaultReferenceStrength,
            referenceOptionsClosed: referenceOptions ? !referenceOptions.open : null,
            outputFrameControls: document.querySelectorAll(
              '#video-source-panel [data-action="reference-frame"]'
            ).length,
            referenceStrength: (() => {
              const control = document.querySelector('#video-source-panel .video-reference-options input[type=range]');
              return control ? [control.min, control.max, control.step, control.value] : null;
            })(),
            seedRange: [
              document.querySelector('#video-seed').min,
              document.querySelector('#video-seed').max,
              document.querySelector('#video-seed').disabled,
              document.querySelector('#video-seed').closest('.field').hidden,
            ],
          };
          capabilities.duration_presets = original.durationPresets;
          capabilities.default_frames = original.defaultFrames;
          capabilities.shapes = original.shapes;
          capabilities.default_shape_ratio = original.defaultShapeRatio;
          capabilities.max_references = original.maxReferences;
          capabilities.min_reference_strength = original.minReferenceStrength;
          capabilities.max_reference_strength = original.maxReferenceStrength;
          capabilities.reference_strength_step = original.referenceStrengthStep;
          capabilities.default_reference_strength = original.defaultReferenceStrength;
          capabilities.min_seed = original.minSeed;
          capabilities.max_seed = original.maxSeed;
          applyVideoCapabilities();
          videoStudio.setModelCapabilities(capabilities);
          capabilities.min_seed = null;
          capabilities.max_seed = null;
          applyVideoCapabilities();
          document.querySelector('#video-seed').value = '22';
          let unsupportedSeedError = '';
          try {
            selectedVideoSeed();
          } catch (error) {
            unsupportedSeedError = error.message;
          }
          document.querySelector('#video-seed').value = '';
          const unsupportedSeed = [
            document.querySelector('#video-seed').disabled,
            document.querySelector('#video-seed').closest('.field').hidden,
            document.querySelector('#video-seed-summary').textContent,
            unsupportedSeedError,
          ];
          state.unsupportedSeed = unsupportedSeed;
          capabilities.min_seed = original.minSeed;
          capabilities.max_seed = original.maxSeed;
          applyVideoCapabilities();
          return state;
        }"""
    )
    check(
        "video settings follow the selected model capability record",
        model_settings
        == {
            "durationRange": ["9", "361", "8", "97"],
            "durations": [
                {"frames": "49", "label": "2 s", "selected": "false"},
                {"frames": "97", "label": "4 s", "selected": "true"},
                {"frames": "145", "label": "6 s", "selected": "false"},
            ],
            "shapes": [
                {"ratio": "5:4", "width": "640", "height": "512", "selected": "false"},
                {"ratio": "4:5", "width": "512", "height": "640", "selected": "true"},
            ],
            "defaultShape": "4.04 seconds, 512 × 640, 97 frames at 24 fps.",  # noqa: RUF001
            "referenceLimit": 2,
            "referenceLimitError": "This video model accepts at most 2 image references.",
            "defaultReferenceStrength": "0.4",
            "referenceOptionsClosed": True,
            "outputFrameControls": 0,
            "referenceStrength": ["0.2", "0.8", "0.2", "0.8"],
            "seedRange": ["17", "99", False, False],
            "unsupportedSeed": [True, True, "Not supported", "This video model does not support a seed."],
        },
        json.dumps(model_settings),
    )
    check(
        "a model without seed support hides its seed control",
        model_settings["unsupportedSeed"] == [True, True, "Not supported", "This video model does not support a seed."],
        str(model_settings["unsupportedSeed"]),
    )
    check(
        "Video keeps one mode selector and places references on its keyframe timeline",
        page.locator("#image-controls .modes").is_hidden()
        and page.locator("#video-controls .modes").count() == 0
        and page.locator("#video-reference-track [data-action='select-reference']").count() == 1,
    )
    output_controls = page.evaluate(
        """() => {
          const duration = document.querySelector('#video-duration').closest('.field').getBoundingClientRect();
          const shape = document.querySelector('.video-ratios').closest('.field').getBoundingClientRect();
          return {durationWidth: duration.width, shapeWidth: shape.width,
            durationTop: duration.top, shapeTop: shape.top};
        }"""
    )
    check(
        "duration and frame shape use balanced full-width groups",
        abs(output_controls["durationWidth"] - output_controls["shapeWidth"]) < 1
        and output_controls["shapeTop"] > output_controls["durationTop"],
        str(output_controls),
    )
    check(
        "keyframe timeline shows one image-anchor track",
        page.locator(".video-studio-head").count() == 0
        and page.locator("#video-timeline .source-track").count() == 0
        and page.locator("#video-reference-track .track-label").text_content() == "Image anchors"
        and page.locator("#video-timeline").get_attribute("aria-label") == "Keyframes"
        and "Keyframes" in page.locator("#video-timeline").inner_text()
        and "1 image" in page.locator("#video-timeline").inner_text()
        and "121 frames" in page.locator("#video-timeline").inner_text()
        and "Images" not in page.locator("#video-timeline").inner_text()
        and page.locator("#video-timeline .render-track").count() == 0
        and "VIDEO WORKSPACE" not in page.locator("#video-timeline").inner_text()
        and "Sequence" not in page.locator("#video-timeline").inner_text()
        and "V1" not in page.locator("#video-timeline").inner_text()
        and "K1" not in page.locator("#video-timeline").inner_text(),
        page.locator("#video-timeline").inner_text(),
    )
    empty_reference_track = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          const saved = {...studio.imageReferences[0]};
          studio.clearImageReferences();
          const visibleWhenEmpty = Boolean(document.querySelector('#video-timeline'));
          const explainsEmptyState = document.querySelector('#video-timeline .timeline-empty')
            ?.textContent.includes('Add an image or capture a frame');
          const hidesTrack = !document.querySelector('#video-timeline .timeline-ruler')
            && !document.querySelector('#video-timeline .timeline-track');
          studio.addImageReference(saved);
          return {visibleWhenEmpty, explainsEmptyState: Boolean(explainsEmptyState), hidesTrack};
        }"""
    )
    check(
        "empty keyframe view hides the full track and explains how to start",
        empty_reference_track == {"visibleWhenEmpty": True, "explainsEmptyState": True, "hidesTrack": True},
        str(empty_reference_track),
    )
    check(
        "video sources stay beside the prompt in the right sidebar",
        page.locator("aside #video-source-panel").count() == 1
        and page.locator(".work #video-source-panel").count() == 0
        and page.locator("#video-timeline").is_visible(),
    )
    check(
        "media panel explains that source clips only provide frames",
        "Only image anchors reach generation" in page.locator("#video-source-panel").inner_text()
        and "Source clips help you pick frames" in page.locator("#video-source-panel").inner_text(),
        page.locator("#video-source-panel").inner_text(),
    )
    desktop_footer = page.evaluate(
        """() => {
          const footer = document.querySelector('#video-footer');
          const form = footer.closest('form');
          const button = document.querySelector('#video-generate');
          return {footerBottom: footer.getBoundingClientRect().bottom,
            formBottom: form.getBoundingClientRect().bottom,
            visible: !footer.hidden && button.getBoundingClientRect().height > 0,
            disabled: button.disabled};
        }"""
    )
    check(
        "video action stays pinned and disabled with an empty prompt",
        desktop_footer["visible"]
        and desktop_footer["disabled"]
        and abs(desktop_footer["footerBottom"] - desktop_footer["formBottom"]) < 2,
        str(desktop_footer),
    )
    page.fill("#video-prompt", "   ")
    check("whitespace does not enable video generation", page.locator("#video-generate").is_disabled())
    page.fill("#video-prompt", "A short camera move")
    check("video prompt enables the generate action", page.locator("#video-generate").is_enabled())
    page.fill("#video-prompt", "")
    page.set_viewport_size({"width": 390, "height": 844})
    mobile_footer = page.evaluate(
        """() => {
          const footer = document.querySelector('#video-footer');
          return {position: getComputedStyle(footer).position,
            bottom: footer.getBoundingClientRect().bottom,
            viewportBottom: window.innerHeight, visible: !footer.hidden};
        }"""
    )
    check(
        "video action stays fixed to the screen on narrow layouts",
        mobile_footer["visible"]
        and mobile_footer["position"] == "fixed"
        and abs(mobile_footer["viewportBottom"] - mobile_footer["bottom"]) < 2,
        str(mobile_footer),
    )
    page.set_viewport_size({"width": 1440, "height": 1000})
    paste_prevented = paste_file(page, REFERENCE.read_bytes(), "clipboard.png", "image/png")
    page.wait_for_function("() => document.querySelectorAll('#video-source-panel .video-reference').length === 2")
    check(
        "pasted images enter video references without changing image references",
        paste_prevented
        and page.locator("#video-source-panel .video-reference").count() == 2
        and page.locator("#thumbs img").count() == 1
        and page.locator("#video-source-panel .video-reference").nth(1).get_attribute("title") == "clipboard.png",
    )
    shortcut_prevented = paste_shortcut_file(page, REFERENCE.read_bytes(), "shortcut.png", "image/png")
    page.wait_for_function("() => document.querySelectorAll('#video-source-panel .video-reference').length === 3")
    check(
        "Command+P pastes an image reference in Video mode",
        shortcut_prevented
        and page.locator("#video-source-panel .video-reference").nth(2).get_attribute("title") == "shortcut.png"
        and "⌘P" in page.locator("#video-source-panel").inner_text(),
        page.locator("#video-source-panel").inner_text(),
    )
    page.get_by_role("button", name="Remove video reference shortcut.png").click()
    page.wait_for_function("() => document.querySelectorAll('#video-source-panel .video-reference').length === 2")
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
    shortcut_prevented = paste_shortcut_file(page, video_bytes, "shortcut.webm", "video/webm")
    page.wait_for_function("() => document.querySelectorAll('#video-source-list .video-source').length === 1")
    check(
        "Command+P pastes a video into source media",
        shortcut_prevented
        and page.locator("#video-gallery .video-clip").count() == 0
        and page.locator("#video-source-list .video-source").count() == 1,
    )
    page.get_by_role("button", name="Remove source video shortcut.webm").click()
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
    source_details = page.locator("#video-output-details").inner_text()
    check(
        "source caption refreshes with loaded video metadata",
        "Source clip" in source_details and "Duration" in source_details and "96 \u00d7 64" in source_details,
        source_details,
    )
    check(
        "imported video files stay in source assets with a timeline",
        page.locator("#video-source-list .video-source").count() == 1
        and page.locator("#video-gallery .video-clip").count() == 0
        and page.locator("#video-timeline").is_visible(),
        f"{page.locator('#video-source-list .video-source').count()} sources",
    )

    page.locator("#video-preview").evaluate("video => { video.currentTime = Math.min(0.4, video.duration / 2); }")
    page.wait_for_function(
        "() => { const video = document.querySelector('#video-preview');"
        "return video && video.currentTime > 0.1 && video.readyState >= 2; }",
        timeout=10000,
    )
    check(
        "source footage uses its own player scrubber",
        page.locator("#video-preview").get_attribute("controls") is not None
        and page.locator("#video-timeline .source-track").count() == 0,
        f"current time {page.locator('#video-preview').evaluate('video => video.currentTime'):.2f}s",
    )
    resume_time = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          const video = document.querySelector('#video-preview');
          const time = video.currentTime;
          studio.setGenerationProgress({running: true, stage: 'running', step: 1, total: 2}, 1);
          studio.setGenerationProgress(null);
          return time;
        }"""
    )
    page.wait_for_function(
        "time => { const video = document.querySelector('#video-preview');"
        "return video && video.readyState >= 2 && Math.abs(video.currentTime - time) < 0.08; }",
        arg=resume_time,
        timeout=10000,
    )
    check(
        "clearing render status restores the source video playhead",
        resume_time > 0.1
        and page.locator("#video-preview").evaluate(
            "(video, time) => Math.abs(video.currentTime - time) < 0.08", resume_time
        ),
        f"restored {resume_time:.2f}s",
    )
    capture_button = page.get_by_role("button", name="Add frame as keyframe")
    expected_capture = page.evaluate(
        """async () => {
          const studio = document.getElementById('video-studio');
          const video = document.querySelector('#video-preview');
          const duration = video.duration;
          const capturedTime = duration * 0.2;
          const laterTime = duration * 0.8;
          video.pause();
          video.currentTime = capturedTime;
          await new Promise(resolve => video.addEventListener('seeked', resolve, {once: true}));
          const originalToBlob = HTMLCanvasElement.prototype.toBlob;
          HTMLCanvasElement.prototype.toBlob = function (callback, type) {
            const canvas = this;
            HTMLCanvasElement.prototype.toBlob = originalToBlob;
            video.currentTime = laterTime;
            video.addEventListener('seeked', () => originalToBlob.call(canvas, callback, type), {once: true});
          };
          const tenths = Math.floor(capturedTime * 10);
          const stamp = String(Math.floor(tenths / 600)).padStart(2, '0') + ':'
            + String(Math.floor(tenths / 10) % 60).padStart(2, '0') + '.' + tenths % 10;
          return {
            frame: Math.round(capturedTime / duration * Math.max(0, studio.frameLimit - 1)),
            name: studio.selectedClip().name + ' frame ' + stamp,
          };
        }"""
    )
    capture_button.focus()
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.querySelectorAll('#video-source-panel .video-reference').length === 2")
    captured_marker = page.locator("#video-reference-track [data-action='select-reference']").nth(1)
    captured_frame_match = re.search(r"Frame (\d+) of", captured_marker.get_attribute("aria-valuetext") or "")
    captured_frame_index = int(captured_frame_match.group(1)) if captured_frame_match else -1
    check(
        "captured pixels and frame metadata use the same source time",
        captured_frame_index == expected_capture["frame"]
        and page.locator("#video-source-panel .video-reference").nth(1).get_attribute("title")
        == expected_capture["name"],
        f"expected {expected_capture}, got frame {captured_frame_index}",
    )
    check(
        "capturing a frame keeps keyboard focus on the capture action",
        page.evaluate("() => document.activeElement?.dataset.action === 'capture-video-frame'"),
    )
    frame_index = captured_frame_index
    marker = page.locator("#video-reference-track [data-action='select-reference']").nth(1)
    marker_position = float(marker.evaluate("element => element.style.left.replace('%', '')"))
    check(
        "reference markers follow their output frame positions",
        page.locator("#video-reference-track [data-action='select-reference']").count() == 2
        and abs(marker_position - frame_index / 120 * 100) < 0.05
        and marker.get_attribute("aria-pressed") == "false",
        f"frame {frame_index} at {marker_position:.2f}%",
    )
    marker.click()
    check(
        "selecting a timeline marker also selects its reference",
        marker.get_attribute("aria-pressed") == "true"
        and "selected" in (page.locator("#video-source-panel .video-reference").nth(1).get_attribute("class") or ""),
    )
    marker.focus()
    before_keyboard_label = marker.get_attribute("aria-valuetext") or ""
    before_keyboard_match = re.search(r"Frame (\d+) of", before_keyboard_label)
    before_keyboard_move = int(before_keyboard_match.group(1)) if before_keyboard_match else -1
    page.keyboard.press("ArrowRight")
    after_keyboard_label = marker.get_attribute("aria-valuetext") or ""
    after_keyboard_match = re.search(r"Frame (\d+) of", after_keyboard_label)
    after_keyboard_move = int(after_keyboard_match.group(1)) if after_keyboard_match else -1
    check(
        "keyboard arrows move a selected reference frame",
        after_keyboard_move == min(120, before_keyboard_move + 1),
        f"frame {before_keyboard_move} to {after_keyboard_move}",
    )
    marker = page.locator("#video-reference-track [data-action='select-reference']").nth(1)
    marker_box = marker.bounding_box()
    rail_box = page.locator("#video-reference-track .timeline-rail").bounding_box()
    page.mouse.move(marker_box["x"] + marker_box["width"] / 2, marker_box["y"] + marker_box["height"] / 2)
    page.mouse.down()
    page.mouse.move(rail_box["x"] + rail_box["width"] * 0.7, marker_box["y"] + marker_box["height"] / 2)
    page.mouse.up()
    pointer_label = marker.get_attribute("aria-valuetext") or ""
    pointer_match = re.search(r"Frame (\d+) of", pointer_label)
    after_pointer_move = int(pointer_match.group(1)) if pointer_match else -1
    check(
        "dragging a reference marker changes its output frame",
        after_pointer_move >= 80,
        f"frame {after_pointer_move}",
    )
    page.get_by_role("button", name="Use current frame in Image").click()
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
        and page.locator("#video-source-panel .video-reference").count() == 3
        and "did not load as a video reference" not in page.locator("#toasts").inner_text(),
        f"video mode: {page.locator('#media-video-mode').get_attribute('aria-pressed')}, "
        f"strip hidden: {page.locator('#strip-wrap').is_hidden()}, "
        f"output clips: {page.locator('#video-gallery .video-clip').count()}, "
        f"video references: {page.locator('#video-source-panel .video-reference').count()}, "
        f"names: {page.locator('#video-source-panel .video-reference').evaluate_all('nodes => nodes.map(node => node.title)')}, "
        f"state: {page.locator('#video-studio').evaluate('element => element.imageReferences.map(item => item.name)')}, "
        f"toast: {page.locator('#toasts').inner_text()}",
    )
    page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          studio.setReferenceFrame(studio.imageReferences[1].id, 300);
        }"""
    )
    page.fill("#video-prompt", "Check the keyframe range")
    page.get_by_role("button", name="Generate video").click()
    page.wait_for_function(
        "() => document.querySelector('#video-request-status').textContent === 'Video generation failed.'",
        timeout=10000,
    )
    check(
        "keyframes outside the selected duration are stopped before the request",
        not video_posts
        and page.locator("#video-studio .video-error").inner_text()
        == "Image reference frames must be between 0 and 120.",
        page.locator("#video-studio .video-error").inner_text(),
    )
    page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          studio.setReferenceFrame(studio.imageReferences[1].id, 9);
        }"""
    )
    page.locator("#video-source-panel .video-reference-options input[type=range]").nth(1).evaluate(
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
        and "576 × 1024" in summary  # noqa: RUF001
        and "241 frames" in summary
        and "24 fps" in summary,
        summary,
    )
    check(
        "keyframe frame bounds follow the selected duration",
        page.locator("#video-reference-track [data-action='select-reference']").nth(1).get_attribute("aria-valuetext")
        == "Frame 9 of 240",
        page.locator("#video-reference-track [data-action='select-reference']").nth(1).get_attribute("aria-valuetext"),
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

    cancel_state = page.evaluate(
        """() => {
          window.__studioOriginalFetch = window.fetch.bind(window);
          window.__studioCancelRequested = false;
          window.__studioProgressReady = false;
          window.__studioForeignRequestId = null;
          window.fetch = (input, options = {}) => {
            const path = new URL(typeof input === 'string' ? input : input.url, location.href).pathname;
            if (path === '/video/generate') {
              window.__studioRequestId = JSON.parse(options.body).request_id;
              return new Promise(resolve => { window.__studioResolveVideo = resolve; });
            }
            if (path === '/video/progress') return Promise.resolve(new Response(JSON.stringify({
              running: window.__studioProgressReady,
              stage: window.__studioProgressReady ? 'running' : 'preparing', step: 2, total: 8, phase: 1,
              kind: 'video', stopping: false,
              request_id: window.__studioForeignRequestId || window.__studioRequestId,
            }), {headers: {'Content-Type': 'application/json'}}));
            if (path === '/video/cancel') {
              window.__studioCancelRequestId = JSON.parse(options.body).request_id;
              window.__studioCancelRequested = true;
              window.__studioResolveVideo(new Response(JSON.stringify({cancelled: true}), {
                headers: {'Content-Type': 'application/json'},
              }));
              return Promise.resolve(new Response(null, {status: 204}));
            }
            return window.__studioOriginalFetch(input, options);
          };
          return true;
        }"""
    )
    pending_clipboard = page.evaluate(
        """() => {
          window.__releaseClipboardRead = null;
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {read: () => new Promise(resolve => { window.__releaseClipboardRead = resolve; })},
          });
          const event = new KeyboardEvent('keydown', {
            key: 'p', metaKey: true, bubbles: true, cancelable: true,
          });
          document.dispatchEvent(event);
          return {prevented: event.defaultPrevented, pending: Boolean(window.__releaseClipboardRead)};
        }"""
    )
    page.evaluate(
        """() => {
          window.__nativeFileReader = window.FileReader;
          window.FileReader = class {
            readAsDataURL() { window.__pendingPasteReader = this; }
          };
        }"""
    )
    pending_reader_paste = paste_file(page, REFERENCE.read_bytes(), "late-reader.png", "image/png")
    check(
        "clipboard and file decoding can both stay pending before a render",
        pending_clipboard["prevented"] and pending_clipboard["pending"] and pending_reader_paste,
    )
    page.fill("#video-seed", "42")
    page.get_by_role("button", name="Generate video").click()
    page.locator("body.video-busy").wait_for(state="attached", timeout=10000)
    starting_locked = page.evaluate(
        """() => ({
          disabled: document.querySelector('#video-generate').disabled,
          label: document.querySelector('#video-generate').textContent,
        })"""
    )
    check(
        "video cancel waits until the server confirms that the run started",
        starting_locked["disabled"] and starting_locked["label"] == "Starting render…",
        str(starting_locked),
    )
    page.evaluate("() => { window.__studioProgressReady = true; }")
    page.evaluate("() => { window.__studioForeignRequestId = 'another-tab'; }")
    page.wait_for_timeout(500)
    foreign_run_state = page.evaluate(
        """() => ({
          disabled: document.querySelector('#video-generate').disabled,
          label: document.querySelector('#video-generate').textContent,
        })"""
    )
    check(
        "another tab cannot unlock this request's cancel button",
        foreign_run_state["disabled"] and foreign_run_state["label"] == "Starting render…",
        str(foreign_run_state),
    )
    page.evaluate("() => { window.__studioForeignRequestId = null; }")
    page.get_by_role("button", name="Cancel render").wait_for(state="visible", timeout=10000)
    cancel_locked = page.evaluate(
        """() => ({
          promptReadOnly: document.querySelector('#video-prompt').readOnly,
          durationPointerLocked: document.querySelector('#video-duration').style.pointerEvents === 'none',
          modeLocked: document.querySelector('#media-image-mode').disabled
            && document.querySelector('#media-video-mode').disabled,
          cancelAvailable: !document.querySelector('#video-generate').disabled
            && document.querySelector('#video-generate').textContent.includes('Cancel'),
          pendingVisible: Boolean(document.querySelector('#video-gallery .video-gallery-pending')),
        })"""
    )
    check(
        "video generation locks the sidebar and offers Cancel beside its status",
        cancel_state
        and cancel_locked["promptReadOnly"]
        and cancel_locked["durationPointerLocked"]
        and cancel_locked["modeLocked"]
        and cancel_locked["cancelAvailable"]
        and cancel_locked["pendingVisible"],
        str(cancel_locked),
    )
    page.evaluate(
        """async () => {
          const studio = document.getElementById('video-studio');
          const blob = await fetch(studio.imageReferences[0].src).then(response => response.blob());
          window.__releaseClipboardRead([{
            name: 'late-clipboard.png', types: ['image/png'], getType: async () => blob,
          }]);
          const reader = window.__pendingPasteReader;
          reader.result = studio.imageReferences[0].src;
          reader.onload();
          window.FileReader = window.__nativeFileReader;
        }"""
    )
    page.wait_for_timeout(150)
    check(
        "async clipboard and file reads cannot add references after a render starts",
        page.locator("#video-source-panel .video-reference").count() == 3
        and page.locator("#video-source-panel").get_by_text("late-clipboard.png").count() == 0
        and page.locator("#video-source-panel").get_by_text("late-reader.png").count() == 0,
        f"references: {page.locator('#video-source-panel .video-reference').count()}",
    )
    blocked_paste_prevented = paste_file(page, REFERENCE.read_bytes(), "late-paste.png", "image/png")
    blocked_shortcut_prevented = paste_shortcut_file(page, REFERENCE.read_bytes(), "late-shortcut.png", "image/png")
    page.wait_for_timeout(100)
    check(
        "clipboard input cannot change references during a locked render",
        blocked_paste_prevented
        and blocked_shortcut_prevented
        and page.locator("#video-source-panel .video-reference").count() == 3
        and page.locator("#video-source-panel").get_by_text("late-paste.png").count() == 0
        and page.locator("#video-source-panel").get_by_text("late-shortcut.png").count() == 0,
        f"references: {page.locator('#video-source-panel .video-reference').count()}",
    )
    page.get_by_role("button", name="Cancel render").click()
    check(
        "video cancellation carries this render's request id",
        page.evaluate("() => window.__studioCancelRequestId === window.__studioRequestId"),
    )
    page.wait_for_function(
        "() => document.querySelector('#video-request-status').textContent === 'Video generation cancelled.'",
        timeout=10000,
    )
    cancel_retained = page.evaluate(
        """() => ({
          requested: window.__studioCancelRequested,
          prompt: document.querySelector('#video-prompt').value,
          references: document.querySelectorAll('#video-source-panel .video-reference').length,
          pending: document.querySelectorAll('#video-gallery .video-gallery-pending').length,
          released: !document.body.classList.contains('video-busy'),
        })"""
    )
    check(
        "cancel stops the request, keeps inputs, and removes the pending gallery tile",
        cancel_retained["requested"]
        and cancel_retained["prompt"]
        and cancel_retained["references"] == 3
        and cancel_retained["pending"] == 0
        and cancel_retained["released"],
        str(cancel_retained),
    )
    page.evaluate("() => { window.fetch = window.__studioOriginalFetch; }")
    page.fill("#video-seed", "")
    sent_frame_match = re.search(
        r"Frame (\d+) of",
        page.locator("#video-reference-track [data-action='select-reference']").nth(1).get_attribute("aria-valuetext")
        or "",
    )
    sent_frame = int(sent_frame_match.group(1)) if sent_frame_match else -1
    sent_strength = float(
        page.locator("#video-source-panel .video-reference-options input[type=range]").nth(1).input_value()
    )
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
        and request.get("width") == 576
        and request.get("height") == 1024
        and len(request.get("references", [])) == 3
        and request.get("seed") is None
        and isinstance(request.get("request_id"), str)
        and len(request.get("request_id", "")) >= 16
        and request["references"][1].get("frame_index") == sent_frame == 9
        and request["references"][1].get("strength") == sent_strength == 0.55
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
    check(
        "a successful video run clears its prompt and image references",
        page.locator("#video-prompt").input_value() == ""
        and page.locator("#video-generate").is_disabled()
        and page.locator("#video-source-panel .video-reference").count() == 0
        and page.locator("#video-reference-count").inner_text() == "0 images"
        and page.locator("#video-source-list .video-source").count() == 1
        and page.locator("#video-duration").input_value() == "241"
        and page.locator("#video-seed").input_value() == "",
        f"prompt: {page.locator('#video-prompt').input_value()!r}, "
        f"image references: {page.locator('#video-source-panel .video-reference').count()}, "
        f"source videos: {page.locator('#video-source-list .video-source').count()}",
    )
    stub_card = page.locator("#video-gallery .video-gallery-item").first
    stub_details = stub_card.inner_text()
    seed_match = re.search(r"Seed\s+(\d+)", page.locator("#video-output-details").inner_text())
    check(
        "selected stub output uses the image-style caption and metadata row",
        "A kite rises as the camera pans across the shore" in page.locator("#video-output-details").inner_text()
        and "576 \u00d7 1024" in page.locator("#video-output-details").inner_text()
        and "24 fps" in page.locator("#video-output-details").inner_text()
        and re.search(r"241 frames", page.locator("#video-output-details").inner_text()) is not None
        and seed_match is not None
        and 0 <= int(seed_match.group(1)) <= 4294967295
        and "3 images" in page.locator("#video-output-details").inner_text()
        and "Request time" in page.locator("#video-output-details").inner_text()
        and page.locator("#video-output-details.stage-bar .prompt-line").count() == 1
        and page.locator("#video-output-details .facts").count() == 1
        and page.locator("#video-output-details .actions").count() == 1
        and "A kite rises as the camera pans across the shore" not in stub_details,
        page.locator("#video-output-details").inner_text(),
    )
    original_stub_prompt = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          const clip = studio.selectedClip();
          const prompt = clip.metadata.prompt;
          clip.metadata.prompt = 'A detailed scene description '.repeat(18);
          studio.renderOutputDetails();
          return prompt;
        }"""
    )
    prompt_button = page.get_by_role("button", name="Read full prompt")
    prompt_button.focus()
    page.keyboard.press("Enter")
    prompt_sheet = page.locator("#video-prompt-sheet")
    prompt_sheet.wait_for(state="visible")
    full_prompt = "A detailed scene description " * 18
    check(
        "keyboard opens the complete video prompt over the preview",
        full_prompt in prompt_sheet.inner_text()
        and page.evaluate("() => document.activeElement?.getAttribute('aria-label')") == "Close full prompt",
    )
    page.locator("#video-source-list .video-source").first.click()
    check(
        "selecting another clip closes the old prompt sheet",
        page.locator("#video-prompt-sheet").count() == 0
        and "demo.webm" in page.locator("#video-output-details").inner_text(),
    )
    page.locator("#video-gallery .video-clip").first.click()
    page.get_by_role("button", name="Read full prompt").focus()
    page.keyboard.press("Enter")
    check(
        "the selected clip can open its own prompt sheet",
        full_prompt in page.locator("#video-prompt-sheet").inner_text(),
    )
    page.keyboard.press("Escape")
    check(
        "Escape closes the full prompt and restores caption focus",
        page.locator("#video-prompt-sheet").count() == 0
        and page.evaluate("() => document.activeElement?.getAttribute('aria-label')") == "Read full prompt",
    )
    page.evaluate(
        """prompt => {
          const studio = document.getElementById('video-studio');
          studio.selectedClip().metadata.prompt = prompt;
          studio.renderOutputDetails();
        }""",
        original_stub_prompt,
    )
    page.evaluate(
        """({videoBytes}) => {
          document.getElementById('video-studio').addGeneratedClip(
            new Blob([new Uint8Array(videoBytes)], {type: 'video/webm'}),
            {
              backend: 'ltx25', modelName: 'LTX-2.5',
              prompt: 'An amber kite crosses a blue sky',
              width: 96, height: 64, numFrames: 12, frameRate: 12,
              duration: 1, seed: 7, elapsedSeconds: 83.2,
              references: [
                {name: 'start.png', frameIndex: 0, strength: 0.4},
                {name: 'end.png', frameIndex: 11, strength: 0.6},
              ],
            },
          );
        }""",
        {"videoBytes": list(video_bytes)},
    )
    thumbnail_ready = False
    try:
        page.wait_for_function(
            "() => { const thumbnail = document.querySelector('#video-gallery .video-clip-thumb img');"
            "return thumbnail && thumbnail.complete && thumbnail.naturalWidth > 0; }",
            timeout=10000,
        )
        thumbnail_ready = True
    except PlaywrightTimeoutError:
        pass
    generated_card = page.locator("#video-gallery .video-gallery-item").nth(1)
    generated_details = page.locator("#video-output-details").inner_text()
    gallery_geometry = page.evaluate(
        """() => {
          const gallery = document.querySelector('#video-gallery').getBoundingClientRect();
          const card = document.querySelector('#video-gallery .video-gallery-item').getBoundingClientRect();
          const thumbnail = document.querySelector('#video-gallery .video-clip-thumb').getBoundingClientRect();
          return {galleryWidth: gallery.width, galleryHeight: gallery.height,
            cardWidth: card.width, thumbnailHeight: thumbnail.height};
        }"""
    )
    output_actions = page.evaluate(
        """() => ({
          downloads: document.querySelectorAll('#video-output-details .video-output-actions a[download]').length,
          downloadName: document.querySelector('#video-output-details .video-output-actions a[download]')?.download,
          more: document.querySelectorAll('#video-output-details .video-output-actions [aria-label="More actions"]').length,
          frameToImage: [...document.querySelectorAll('#video-output-details button')]
            .some(button => button.textContent.includes('Use current frame in Image')),
          referenceTitle: document.querySelector('#video-output-details .video-output-references')?.title,
          menus: document.querySelectorAll('#video-output-menu').length,
          menuItems: document.querySelectorAll('#video-output-menu [role="menuitem"]')
            .length,
        })"""
    )
    check(
        "video gallery uses the compact Image filmstrip scale",
        gallery_geometry["cardWidth"] <= 120
        and gallery_geometry["thumbnailHeight"] <= 65
        and gallery_geometry["galleryHeight"] <= 132
        and page.locator("#video-gallery .video-clips.strip").count() == 1
        and page.locator("#video-gallery .video-clip.frame").count() == 2
        and page.locator("#video-gallery .video-clip-remove").count() == 0,
        str(gallery_geometry),
    )
    check(
        "generated gallery thumbnail and output metadata appear with the clip",
        thumbnail_ready
        and generated_card.locator(".video-clip-thumb img").count() == 1
        and "96 \u00d7 64" in generated_details
        and "12 fps" in generated_details
        and re.search(r"12 frames", generated_details) is not None
        and re.search(r"Seed\s+7", generated_details) is not None
        and "2 images" in generated_details
        and "Took 01:23.2" in generated_details
        and "01:23.2" in generated_details
        and "An amber kite crosses a blue sky" in generated_details
        and "start.png at frame 0" in generated_details
        and "end.png at frame 11" in generated_details
        and page.locator("#video-output-details .video-output-actions a[download]").count() == 1
        and page.locator("#video-output-details .video-output-actions a[download]").get_attribute("download")
        == "LTX-2.5 1s.webm"
        and page.locator("#video-output-details .video-output-actions [aria-label='More actions']").count() == 1
        and page.get_by_role("button", name="Use current frame in Image").is_visible()
        and page.locator("#video-output-details .video-output-references").get_attribute("title")
        == "start.png, frame 0, strength 0.40, end.png, frame 11, strength 0.60"
        and page.locator("#video-timeline .source-track").count() == 0,
        generated_details
        + "\n"
        + json.dumps(
            {
                **output_actions,
                "thumbnailReady": thumbnail_ready,
                "thumbnailCount": generated_card.locator(".video-clip-thumb img").count(),
            }
        ),
    )
    page.get_by_role("button", name="More actions").click()
    check(
        "video more actions match the image action menu",
        page.get_by_role("menuitem", name="Reuse prompt").is_visible()
        and page.get_by_role("menuitem", name="Reuse seed 7").is_visible()
        and page.get_by_role("menuitem", name="Remove video LTX-2.5 1s").is_visible(),
        page.locator("#video-output-menu").inner_text(),
    )
    page.get_by_role("menuitem", name="Reuse prompt").click()
    check(
        "video prompt can be reused from its selected output",
        page.locator("#video-prompt").input_value() == "An amber kite crosses a blue sky",
        page.locator("#video-prompt").input_value(),
    )
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Reuse seed 7").click()
    check(
        "video seed can be reused from its selected output",
        page.locator("#video-seed").input_value() == "7"
        and page.locator("#video-advanced").evaluate("element => element.open"),
        page.locator("#video-seed").input_value(),
    )
    progress_result = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          if (typeof studio.setGenerationProgress !== 'function') return {supported: false};
          studio.setGenerationProgress(
            {running: true, stage: 'preparing', step: 0, total: 0}, 5.2,
            {width: 512, height: 640, modelName: 'LTX-2.5'});
          const preparing = document.querySelector('#video-preview-root #video-render-progress');
          const preparingText = preparing && preparing.getAttribute('aria-valuetext');
          const preparingIndeterminate = Boolean(preparing && preparing.classList.contains('is-indeterminate'));
          const preparingHasNoPercent = Boolean(preparing && !preparing.hasAttribute('aria-valuenow'));
          studio.setGenerationProgress({running: true, stage: 'running', step: 4, total: 8, phase: 2}, 6.4);
          const previewStatus = document.querySelector('#video-preview-root #video-render-status');
          const previewProgress = document.querySelector('#video-preview-root #video-render-progress');
          const preview = document.querySelector('#video-preview');
          const timeline = document.querySelector('#video-timeline .render-track');
          const pendingTile = document.querySelector('#video-gallery .video-gallery-pending');
          const previewStatusStyle = previewStatus && getComputedStyle(previewStatus);
          const stage = document.querySelector('#video-preview-root');
          const statusBox = previewStatus && previewStatus.getBoundingClientRect();
          const stageBox = stage && stage.getBoundingClientRect();
          const result = {
            supported: true,
            preparingText,
            preparingIndeterminate,
            preparingHasNoPercent,
            previewStatus: previewStatus && previewStatus.innerText,
            previewModel: previewStatus && previewStatus.querySelector('.video-render-brand').innerText,
            previewPercent: previewProgress && previewProgress.getAttribute('aria-valuenow'),
            hasPlaybackIcon: Boolean(previewStatus && previewStatus.querySelector('.video-render-mark')),
            pendingTile: Boolean(pendingTile && pendingTile.innerText.includes('Rendering')),
            pendingGalleryCount: document.querySelectorAll('#video-gallery .video-gallery-pending').length,
            previewReplaced: !preview,
            statusIsThumbnail: Boolean(previewStatusStyle && previewStatusStyle.position !== 'absolute'
              && statusBox && stageBox && statusBox.width > 0 && statusBox.height > 0
              && statusBox.left >= stageBox.left && statusBox.right <= stageBox.right
              && statusBox.top >= stageBox.top && statusBox.bottom <= stageBox.bottom),
            thumbnailRatio: statusBox && statusBox.width / statusBox.height,
            timelineHasRenderTrack: Boolean(timeline),
          };
          studio.setGenerationProgress(null);
          result.previewStatusCleared = !document.querySelector('#video-preview-root #video-render-status');
          result.previewStillVisible = Boolean(document.querySelector('#video-preview')
            && !document.querySelector('#video-preview').hidden);
          return result;
        }"""
    )
    check(
        "video model loading uses indeterminate progress",
        (progress_result.get("preparingText") or "").startswith("Loading LTX-2.5")
        and progress_result.get("preparingIndeterminate")
        and progress_result.get("preparingHasNoPercent"),
        str(progress_result),
    )
    check(
        "video preview displays named stage progress without playback controls",
        progress_result.get("supported")
        and (progress_result.get("preparingText") or "").startswith("Loading LTX-2.5")
        and "LTX-2.5" in progress_result.get("previewModel", "")
        and "Upscaling and refining" in progress_result.get("previewStatus", "")
        and "Pass" not in progress_result.get("previewStatus", "")
        and progress_result.get("previewPercent") == "50"
        and not progress_result.get("hasPlaybackIcon")
        and progress_result.get("pendingTile")
        and progress_result.get("pendingGalleryCount") == 1
        and progress_result.get("previewReplaced")
        and progress_result.get("statusIsThumbnail")
        and abs(progress_result.get("thumbnailRatio", 0) - 0.8) < 0.02,
        str(progress_result),
    )
    check(
        "video timeline has no duplicate render progress track",
        not progress_result.get("timelineHasRenderTrack"),
        str(progress_result),
    )
    check(
        "video preview status clears after render while the clip stays visible",
        progress_result.get("previewStatusCleared") and progress_result.get("previewStillVisible"),
        str(progress_result),
    )
    page.set_viewport_size({"width": 390, "height": 844})
    mobile_status = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          studio.setGenerationProgress({running: true, stage: 'running', step: 4, total: 8, phase: 2}, 6.4);
          const status = document.querySelector('#video-render-status');
          const preview = document.querySelector('#video-preview-root');
          const statusBox = status.getBoundingClientRect();
          const previewBox = preview.getBoundingClientRect();
          const result = {
            visible: Boolean(status && statusBox.width > 0 && statusBox.height > 0),
            insidePreview: statusBox.left >= previewBox.left
              && statusBox.right <= previewBox.right
              && statusBox.top >= previewBox.top
              && statusBox.bottom <= previewBox.bottom,
            width: statusBox.width,
            previewWidth: previewBox.width,
          };
          studio.setGenerationProgress(null);
          return result;
        }"""
    )
    page.set_viewport_size({"width": 1440, "height": 1000})
    check(
        "video render status fits the preview on a phone viewport",
        mobile_status.get("visible") and mobile_status.get("insidePreview"),
        str(mobile_status),
    )
    try:
        page.wait_for_function(
            """async () => {
              const request = indexedDB.open('studio');
              const database = await new Promise((resolve, reject) => {
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
              });
              if (!database.objectStoreNames.contains('videos')) return false;
              const transaction = database.transaction('videos', 'readonly');
              const records = await new Promise((resolve, reject) => {
                const query = transaction.objectStore('videos').getAll();
                query.onsuccess = () => resolve(query.result);
                query.onerror = () => reject(query.error);
              });
              return records.length === 1 && records[0].mp4 instanceof Blob
                && records[0].mp4.size > 0 && records[0].metadata.prompt === 'An amber kite crosses a blue sky';
            }""",
            timeout=10000,
        )
        video_saved = True
    except PlaywrightTimeoutError:
        video_saved = False
    page.reload()
    switch_workspace(page, "video")
    try:
        page.wait_for_function(
            "() => document.querySelectorAll('#video-gallery .video-clip').length === 1",
            timeout=10000,
        )
        restored = page.locator("#video-gallery .video-gallery-item").first
        restored_count = page.locator("#video-gallery .video-clip").count()
        restored_details = page.locator("#video-output-details").inner_text()
        restored_thumbnail = restored.locator(".video-clip-thumb img").count() == 1
        restored_video = page.wait_for_function(
            """() => {
              const video = document.querySelector('#video-preview');
              return video && video.readyState >= 2 && video.videoWidth === 96;
            }""",
            timeout=10000,
        )
    except PlaywrightTimeoutError:
        restored_count = page.locator("#video-gallery .video-clip").count()
        restored_details = ""
        restored_thumbnail = False
        restored_video = False
    check(
        "generated video and metadata survive a browser reload",
        video_saved
        and restored_count == 1
        and "An amber kite crosses a blue sky" in restored_details
        and "Took 01:23.2" in restored_details
        and "01:23.2" in restored_details
        and restored_thumbnail
        and restored_video,
        f"saved: {video_saved}, restored clips: {restored_count}, details: {restored_details}",
    )
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Remove video LTX-2.5 1s").click()
    page.wait_for_function("() => document.querySelector('#video-gallery .video-clip') === null", timeout=10000)
    page.reload()
    switch_workspace(page, "video")
    page.wait_for_function("() => document.querySelector('#video-gallery .video-clip') === null", timeout=10000)
    check(
        "removing a video also removes its saved copy",
        page.locator("#video-gallery .video-clip").count() == 0,
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
