"""Check image and video handoffs against the local stub server.

uv run studio --stub --port <port>
uv run --with playwright python tests/e2e/verify_media_studio.py <port>
"""

import base64
import json
import re
import shutil
import sys
import tempfile
import urllib.parse
import wave
from pathlib import Path

from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

PORT = sys.argv[1]
URL = f"http://127.0.0.1:{PORT}/"
SCRATCH = Path(tempfile.mkdtemp(prefix="verify-media-studio-"))
REFERENCE = SCRATCH / "reference.png"
Image.new("RGB", (1024, 1024), (194, 89, 42)).save(REFERENCE)
AUDIO = SCRATCH / "theme.wav"
with wave.open(str(AUDIO), "wb") as track:
    track.setnchannels(1)
    track.setsampwidth(2)
    track.setframerate(16000)
    track.writeframes(b"\x00\x00" * 16000)
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
    downloads = []
    page.on("download", lambda download: downloads.append(download.suggested_filename))
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
    image_mode_layout = page.evaluate(
        """() => {
          const controls = document.querySelector('#image-controls');
          const modes = controls.querySelector('.modes');
          const prompt = controls.querySelector('.prompt-field');
          const label = modes.querySelector('label').getBoundingClientRect();
          return {
            selectorBeforePrompt: Boolean(modes.compareDocumentPosition(prompt)
              & Node.DOCUMENT_POSITION_FOLLOWING),
            selectorHeight: label.height,
            videoSelectorIsItsOwn: document.querySelector('#video-controls .modes')?.id === 'video-modes',
          };
        }"""
    )
    switch_workspace(page, "video")
    switch_workspace(page, "image")
    check(
        "Image Generate and Edit keep their original selector above Prompt",
        image_mode_layout["selectorBeforePrompt"]
        and image_mode_layout["selectorHeight"] == 32
        and image_mode_layout["videoSelectorIsItsOwn"],
        str(image_mode_layout),
    )
    page.set_viewport_size({"width": 1024, "height": 844})
    page.locator("label[for=mode-edit]").click()
    page.locator("#templates-toggle").evaluate("button => { button.hidden = false; }")
    page.locator("#rewrite-toggle").evaluate("button => { button.hidden = false; button.disabled = false; }")
    narrow_prompt_head = page.evaluate(
        """() => {
          const head = document.querySelector('#image-controls .prompt-field .field-head');
          const bounds = head.getBoundingClientRect();
          const controls = [...head.querySelectorAll('.head-actions, #templates-toggle, #rewrite-toggle')];
          const left = Math.min(...controls.map(control => control.getBoundingClientRect().left));
          const right = Math.max(...controls.map(control => control.getBoundingClientRect().right));
          const label = head.querySelector(':scope > label').getBoundingClientRect();
          const actions = head.querySelector('.head-actions').getBoundingClientRect();
          const overlaps = (first, second) => first.left < second.right && first.right > second.left
            && first.top < second.bottom && first.bottom > second.top;
          const modes = document.querySelector('#image-controls .modes');
          return {width: bounds.width, clientWidth: head.clientWidth, scrollWidth: head.scrollWidth,
            left, headerLeft: bounds.left, right, headerRight: bounds.right,
            labelActionsOverlap: overlaps(label, actions),
            modeFitsSidebar: modes.getBoundingClientRect().right <= bounds.right + 1};
        }"""
    )
    check(
        "Edit prompt controls fit in a narrow sidebar",
        narrow_prompt_head["scrollWidth"] <= narrow_prompt_head["clientWidth"]
        and narrow_prompt_head["left"] >= narrow_prompt_head["headerLeft"] - 1
        and narrow_prompt_head["right"] <= narrow_prompt_head["headerRight"] + 1
        and not narrow_prompt_head["labelActionsOverlap"]
        and narrow_prompt_head["modeFitsSidebar"],
        str(narrow_prompt_head),
    )
    # The video prompt's head carries the same two controls, so it is measured at the same
    # width. Its own buttons are driven by the stub's capabilities, which offer both.
    switch_workspace(page, "video")
    video_models = page.evaluate(
        "() => [...document.querySelectorAll('#backend-menu [role=menuitemradio]')].map((item) => item.getAttribute('aria-label'))"
    )
    video_default = page.evaluate("() => document.getElementById('backend-toggle').querySelector('.name').textContent")
    video_catalog = page.request.get(URL + "api/v1/state").json()["studio"]["video"]["backends"]
    check(
        "Video shows LTX-2.5 without a picker and the API offers only that model",
        video_default == "LTX-2.5"
        and video_models == []
        and page.locator("#backend-toggle").is_disabled()
        and not page.locator("#backend-toggle .icon").is_visible()
        and [model["id"] for model in video_catalog] == ["ltx25_mlx"],
        str({"default": video_default, "models": video_models}),
    )
    narrow_video_head = page.evaluate(
        """() => {
          const head = document.querySelector('#video-controls .prompt-field .field-head');
          const bounds = head.getBoundingClientRect();
          const controls = [...head.querySelectorAll('.head-actions, #video-templates-toggle, #video-rewrite-toggle')];
          const left = Math.min(...controls.map(control => control.getBoundingClientRect().left));
          const right = Math.max(...controls.map(control => control.getBoundingClientRect().right));
          const label = head.querySelector(':scope > label').getBoundingClientRect();
          const actions = head.querySelector('.head-actions').getBoundingClientRect();
          const overlaps = (first, second) => first.left < second.right && first.right > second.left
            && first.top < second.bottom && first.bottom > second.top;
          return {clientWidth: head.clientWidth, scrollWidth: head.scrollWidth,
            left, headerLeft: bounds.left, right, headerRight: bounds.right,
            labelActionsOverlap: overlaps(label, actions),
            // Only the pills that are shown: the adapter's own pill lives here too and is
            // hidden unless the mode offers adapters, and a hidden pill takes no room.
            headPills: [...document.querySelectorAll('#video-controls .head-actions .pill')]
              .filter(pill => !pill.hidden).length};
        }"""
    )
    switch_workspace(page, "image")
    check(
        "the video prompt controls fit in a narrow sidebar too",
        narrow_video_head["scrollWidth"] <= narrow_video_head["clientWidth"]
        and narrow_video_head["left"] >= narrow_video_head["headerLeft"] - 1
        and narrow_video_head["right"] <= narrow_video_head["headerRight"] + 1
        and not narrow_video_head["labelActionsOverlap"]
        and narrow_video_head["headPills"] == 2,
        str(narrow_video_head),
    )
    # The adapter's pill is the third one in that same head, and it shows only in a mode that
    # offers adapters. It has to fit there too, beside the two that are always shown.
    switch_workspace(page, "video")
    page.evaluate("() => document.querySelector('#video-modes input[value=edit]').click()")
    narrow_edit_head = page.evaluate(
        """() => {
          const head = document.querySelector('#video-controls .prompt-field .field-head');
          const shown = [...head.querySelectorAll('.head-actions .pill')].filter(pill => !pill.hidden);
          const bounds = shown.map(pill => pill.getBoundingClientRect());
          return {pills: shown.map(pill => pill.id), clientWidth: head.clientWidth,
            scrollWidth: head.scrollWidth,
            insideHeader: bounds.every(box => box.left >= head.getBoundingClientRect().left - 1
              && box.right <= head.getBoundingClientRect().right + 1)};
        }"""
    )
    switch_workspace(page, "image")
    page.evaluate("() => document.querySelector('#video-modes input[value=generate]').click()")
    check(
        "edit mode puts the adapter and Rewrite in the prompt's head, and the templates away",
        narrow_edit_head["pills"] == ["video-adapters-toggle", "video-rewrite-toggle"]
        and narrow_edit_head["scrollWidth"] <= narrow_edit_head["clientWidth"]
        and narrow_edit_head["insideHeader"],
        str(narrow_edit_head),
    )
    page.locator("label[for=mode-generate]").click()
    page.set_viewport_size({"width": 1440, "height": 1000})
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
    # studio.toml offers one image model, so the page draws no picker to open: the
    # toggle names that model and stays shut. The video check below reads the same way.
    check(
        "Image mode shows its own selected model, with no picker",
        page.locator("#backend-toggle .name").inner_text() == "Qwen-Image-2.1-Turbo"
        and page.locator("#backend-toggle").is_disabled(),
        page.locator("#backend-toggle").inner_text().replace("\n", " "),
    )

    page.fill("#prompt", "A copper cup on a wooden table")
    page.dispatch_event("#prompt", "input")
    check(
        "Turbo text generation shows its measured time estimate",
        page.locator("#go-sub").inner_text() == "about 10s",
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
        page.locator("#go-sub").inner_text() == "about 10s",
        page.locator("#go-sub").inner_text(),
    )
    page.locator("#strength").evaluate(
        "element => { element.value = '0.8'; element.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    check(
        "Turbo reference estimate follows image strength",
        page.locator("#go-sub").inner_text() == "about 5s",
        page.locator("#go-sub").inner_text(),
    )
    page.locator("#strength").evaluate(
        "element => { element.value = '0.4'; element.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.get_by_role("button", name="Share references with Video").click()
    page.wait_for_function("() => document.querySelector('#media-video-mode').getAttribute('aria-pressed') === 'true'")
    page.locator("#video-references .video-reference").wait_for(state="visible")
    check(
        "image references transfer to the video workspace",
        page.locator("#video-source-panel .video-reference").get_attribute("title") == "reference.png",
        page.locator("#video-source-panel .video-reference").get_attribute("title") or "no reference",
    )
    check(
        "a reference is its print and its name, with no influence dial",
        page.locator("#video-source-panel .video-reference-options").count() == 0
        and page.locator("#video-source-panel .video-reference-name").inner_text() == "reference.png"
        and page.locator("#video-source-panel [data-action='reference-frame']").count() == 0,
        page.locator("#video-source-panel .video-reference").inner_text(),
    )
    check(
        "Video mode shows its own selected model without a picker",
        page.locator("#backend-toggle .name").inner_text() == "LTX-2.5"
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
          videoStudio.addImageReference({...reference, id: 'model-limit-two', name: reference.name + ' b'});
          const referenceLimitError = videoStudio.error;
          const defaultReferenceStrength = videoStudio.defaultReferenceStrength;
          const referenceOptions = document.querySelectorAll('.video-reference-options').length;
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
              selected: button.getAttribute('aria-pressed'),
            })),
            resolutions: [...document.querySelectorAll('#video-resolutions button')].map(button => ({
              width: button.dataset.width,
              height: button.dataset.height,
              label: button.textContent,
              selected: button.getAttribute('aria-pressed'),
            })),
            resolutionRowHidden: document.querySelector('#video-resolutions').closest('.field').hidden,
            defaultShape: document.querySelector('#video-frame-count').textContent,
            referenceLimit: videoStudio.maxReferences,
            referenceLimitError: referenceLimitError,
            defaultReferenceStrength: defaultReferenceStrength,
            referenceOptions: referenceOptions,
            outputFrameControls: document.querySelectorAll(
              '#video-source-panel [data-action="reference-frame"]'
            ).length,
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
                {"ratio": "5:4", "selected": "false"},
                {"ratio": "4:5", "selected": "true"},
            ],
            # One size for a shape is not a ladder, so that record carries no resolution row.
            "resolutions": [],
            "resolutionRowHidden": True,
            "defaultShape": "512 × 640, 97 frames",  # noqa: RUF001
            "referenceLimit": 2,
            "referenceLimitError": "This video model accepts at most 2 image references.",
            "defaultReferenceStrength": 0.4,
            "referenceOptions": 0,
            "outputFrameControls": 0,
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

    # The resolution ladder on the model's own record: the sizes for each shape, lowest
    # first, so a prompt can be tried on a small frame before it is worth four minutes.
    # Every shape opens on its lowest rung, including one reached by a shape change: a rung
    # picked on one shape does not follow the shape. The wide frame's third rung is put back
    # at the end, because the checks below read the shape the suite has been working in.
    ladder = page.evaluate(
        """() => {
          const rows = () => [...document.querySelectorAll('#video-resolutions button')].map(button => ({
            size: button.dataset.width + 'x' + button.dataset.height,
            label: button.textContent,
            selected: button.getAttribute('aria-pressed'),
          }));
          const caption = () => document.getElementById('video-frame-count').textContent;
          applyVideoCapabilities();
          const open = {rows: rows(), hidden: document.querySelector('#video-resolutions').closest('.field').hidden};
          document.querySelector('#video-resolutions button').click();
          const low = {rows: rows(), caption: caption()};
          document.querySelector('.video-ratios button[data-ratio="9:16"]').click();
          const tall = {rows: rows(), caption: caption()};
          document.querySelector('.video-ratios button[data-ratio="16:9"]').click();
          const back = {rows: rows()};
          document.querySelectorAll('#video-resolutions button')[2].click();
          const full = {rows: rows(), caption: caption()};
          document.querySelector('.video-ratios button[data-ratio="9:16"]').click();
          const movedHigh = {rows: rows(), caption: caption()};
          document.querySelector('.video-ratios button[data-ratio="16:9"]').click();
          const returned = {rows: rows()};
          document.querySelectorAll('#video-resolutions button')[2].click();
          return {open, low, tall, back, full, movedHigh, returned};
        }"""
    )
    check(
        "the resolution row offers each shape's sizes, lowest first, on the model's own record",
        [row["size"] for row in ladder["open"]["rows"]] == ["384x384", "512x512", "768x768"]
        and [row["label"] for row in ladder["open"]["rows"]] == ["384p", "512p", "768p"]
        and [row["selected"] for row in ladder["open"]["rows"]] == ["true", "false", "false"]
        and not ladder["open"]["hidden"],
        json.dumps(ladder["open"]),
    )
    check(
        "a low rung is the frame the caption names",
        ladder["low"]["caption"] == "384 × 384, 121 frames"  # noqa: RUF001
        and ladder["low"]["rows"][0]["selected"] == "true",
        json.dumps(ladder["low"]),
    )
    check(
        "each shape opens on its lowest rung",
        [row["size"] for row in ladder["tall"]["rows"]] == ["384x640", "448x768", "576x1024", "1088x1920"]
        and ladder["tall"]["rows"][0]["selected"] == "true"
        and "384 × 640" in ladder["tall"]["caption"]  # noqa: RUF001
        and [row["selected"] for row in ladder["back"]["rows"]] == ["true", "false", "false", "false", "false"],
        json.dumps(ladder["tall"]),
    )
    check(
        "a rung picked on one shape does not follow the shape",
        [row["selected"] for row in ladder["full"]["rows"]] == ["false", "false", "true", "false", "false"]
        and [row["selected"] for row in ladder["movedHigh"]["rows"]] == ["true", "false", "false", "false"]
        and ladder["movedHigh"]["caption"] == "384 × 640, 121 frames"  # noqa: RUF001
        and [row["selected"] for row in ladder["returned"]["rows"]] == ["true", "false", "false", "false", "false"],
        json.dumps(ladder["movedHigh"]),
    )
    # The video prompt's own templates. The record decides the menu, and a template that names
    # the reference image is offered only while the video carries one: the page reads that
    # from the phrase, so this drives it with a record of its own and then puts the real one
    # back. The fill is checked on the real record, bracket selected for the first Tab.
    template_menu = page.evaluate(
        """() => {
          const capabilities = videoCapabilities();
          const original = capabilities.templates;
          capabilities.templates = [
            {name: 'Plain one', hint: 'no reference named', text: 'A plain sentence about [something].'},
            {name: 'Needs a still', hint: 'names the reference image',
             text: 'Keep the first frame as the reference image.'},
          ];
          applyVideoCapabilities();
          document.getElementById('video-templates-toggle').click();
          const offered = [...document.querySelectorAll('#video-templates [role=menuitem]')]
            .map(item => item.innerText.split('\\n')[0]);
          menus.closeMenus();
          capabilities.templates = original;
          applyVideoCapabilities();
          return {
            offered,
            references: document.getElementById('video-studio').imageReferences.length,
            declared: (original || []).map(template => template.name),
            first: original && original.length ? original[0].text : '',
          };
        }"""
    )
    check(
        "a video template that names the reference image is offered only while the video has one",
        template_menu["offered"] == (["Plain one", "Needs a still"] if template_menu["references"] else ["Plain one"]),
        json.dumps(template_menu),
    )
    page.locator("#video-templates-toggle").click()
    page.get_by_role("menuitem", name="Camera move").click()
    filled = page.evaluate(
        """() => {
          const prompt = document.getElementById('video-prompt');
          const button = document.getElementById('video-rewrite-toggle');
          const result = {
            value: prompt.value,
            selected: prompt.value.slice(prompt.selectionStart, prompt.selectionEnd),
            // A template is written into the box without a keystroke, so this is where the
            // rewrite button has to have heard about it: it reads the box for its own state.
            rewriteAwake: !button.disabled,
            rewriteTitle: button.title,
            // Read here, because this block empties the box on its way out and the run
            // button is dead the moment it is empty. A template leaves its brackets for the
            // user to fill, so the run waits, the way the image form's does.
            runAwake: !document.getElementById('video-generate').disabled,
          };
          prompt.value = prompt.value.replace(/\\[[^\\]\\n]+\\]/g, 'a cyclist');
          prompt.dispatchEvent(new Event('input', { bubbles: true }));
          result.runAwakeWhenFilled = !document.getElementById('video-generate').disabled;
          // The checks below read an empty prompt, so this puts it back the way it found it,
          // through the same door a template writes it: a plain value change raises nothing.
          prompt.value = '';
          prompt.dispatchEvent(new Event('input', { bubbles: true }));
          return result;
        }"""
    )
    check(
        "the video prompt menu lists the model's templates and fills one with its bracket selected",
        template_menu["declared"][:1] == ["Camera move"]
        and filled["value"] == template_menu["first"]
        and filled["selected"].startswith("[")
        and filled["selected"].endswith("]"),
        json.dumps(filled),
    )
    check(
        "a template wakes the rewrite button, and the run waits until its brackets are filled",
        filled["rewriteAwake"]
        and "longer instruction" in filled["rewriteTitle"]
        and not filled["runAwake"]
        and filled["runAwakeWhenFilled"],
        json.dumps(filled),
    )

    # Each template menu hangs 6px under its own button row, and one rule draws both. The
    # video menu used to take the shared `.menu` rule instead, which puts a menu 6px under
    # the whole field: that dropped it 126px, over the Media section.
    def menu_drop(toggle, menu):
        page.click(toggle)
        page.wait_for_timeout(150)
        measured = page.evaluate(
            """([toggle, menu]) => {
              const button = document.querySelector(toggle).getBoundingClientRect();
              const panel = document.querySelector(menu).getBoundingClientRect();
              const sidebar = document.querySelector('.controls').getBoundingClientRect();
              return {drop: panel.top - button.bottom, inside: panel.right <= sidebar.right + 1
                && panel.left >= sidebar.left - 1};
            }""",
            [toggle, menu],
        )
        page.keyboard.press("Escape")
        return measured

    video_drop = menu_drop("#video-templates-toggle", "#video-templates")
    switch_workspace(page, "image")
    image_drop = menu_drop("#templates-toggle", "#templates")
    switch_workspace(page, "video")
    check(
        "each template menu opens 6px under its own button row, inside the sidebar",
        abs(video_drop["drop"] - 6) <= 1
        and abs(image_drop["drop"] - 6) <= 1
        and video_drop["inside"]
        and image_drop["inside"],
        json.dumps({"video": video_drop, "image": image_drop}),
    )

    # The video prompt's rewrite: the same rewriter the image form uses for a generate
    # prompt, reached from the video prompt's own box. The stub writes in slices on a short
    # clock, so the press, its readout and its cancel are all checked here without a GPU.
    check(
        "the video prompt offers a rewrite",
        page.locator("#video-rewrite-toggle").is_visible() and page.locator("#video-rewrite-toggle").is_disabled(),
        page.get_attribute("#video-rewrite-toggle", "title"),
    )
    page.fill("#video-prompt", "a cat walking on a wall")
    check(
        "a prompt wakes the rewrite button",
        not page.locator("#video-rewrite-toggle").is_disabled(),
        page.get_attribute("#video-rewrite-toggle", "title"),
    )
    page.click("#video-rewrite-toggle")
    page.wait_for_timeout(200)
    check(
        "a press shows one verb and borrows the readout",
        page.inner_text("#video-rewrite-toggle") == "Rewrite"
        and page.locator("#shared-operation").is_visible()
        and "Preparing" in page.inner_text("#shared-operation-label"),
        f"{page.inner_text('#video-rewrite-toggle')!r}, {page.inner_text('#shared-operation-label')!r}",
    )
    page.locator("#video-rewrite-toggle .rewrite-cancel").wait_for(state="visible")
    check(
        "Cancel arrives once it writes, and the panel and the run button are held",
        page.locator("#form").get_attribute("data-panel-held") == "true"
        and page.locator("#video-prompt").get_attribute("readonly") is not None
        and page.locator("#video-generate").is_disabled(),
        page.inner_text("#shared-operation-label"),
    )
    page.wait_for_function("document.getElementById('video-prompt').value.indexOf('stub') >= 0")
    check(
        "the answer lands in the video prompt, and the page lets go of the panel",
        page.input_value("#video-prompt") == "a cat walking on a wall A longer version of it, written for the stub."
        and page.locator("#form").get_attribute("data-panel-held") is None
        and not page.locator("#video-generate").is_disabled(),
        page.input_value("#video-prompt"),
    )
    page.fill("#video-prompt", "a dog in a field")
    page.click("#video-rewrite-toggle")
    page.locator("#video-rewrite-toggle .rewrite-cancel").wait_for(state="visible")
    page.click("#video-rewrite-toggle")
    page.locator("#video-rewrite-toggle .rewrite-stopping").wait_for(state="visible")
    page.wait_for_function("document.querySelector('#form').dataset.panelHeld === undefined")
    check(
        "a cancel keeps the words that were typed",
        page.input_value("#video-prompt") == "a dog in a field"
        and page.locator("#video-rewrite-toggle .rewrite-idle").is_visible()
        and not page.locator("#video-generate").is_disabled(),
        page.input_value("#video-prompt"),
    )
    # The checks below read an empty prompt, so this puts it back the way it found it.
    page.fill("#video-prompt", "")
    check(
        "an emptied prompt puts the rewrite button back to dead",
        page.locator("#video-rewrite-toggle").is_disabled() and page.locator("#video-generate").is_disabled(),
    )
    video_modes = page.evaluate(
        """() => {
          const modes = document.querySelector('#video-controls .modes');
          const label = modes.querySelector('label').getBoundingClientRect();
          return {count: document.querySelectorAll('#video-controls .modes').length,
            visible: !modes.hidden, height: label.height,
            radios: modes.querySelectorAll('input[type=radio]').length,
            // The columns themselves resolve to pixels, so what is compared is their number
            // and the gap between them: the same grid the image form draws.
            sameStylesAsImage: getComputedStyle(modes).gridTemplateColumns.split(' ').length
              === getComputedStyle(document.querySelector('#image-controls .modes')).gridTemplateColumns.split(' ').length
              && getComputedStyle(modes).gap === getComputedStyle(document.querySelector('#image-controls .modes')).gap};
        }"""
    )
    check(
        "Video has the Image selector's own switch, and puts references in the sidebar",
        page.locator("#image-controls .modes").is_hidden()
        and video_modes["count"] == 1
        and video_modes["visible"]
        and video_modes["radios"] == 2
        and video_modes["height"] == 32
        and video_modes["sameStylesAsImage"]
        and page.locator("#video-reference-tray[aria-label='Image references']").count() == 1
        and page.locator("#video-reference-track").count() == 0,
        json.dumps(video_modes),
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
    empty_reference_list = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          const saved = {...studio.imageReferences[0]};
          studio.clearImageReferences();
          const timelineCount = document.querySelectorAll('#video-timeline, #video-reference-track').length;
          const emptyState = document.querySelector('#video-media-empty');
          const sourceGroup = document.querySelector('.video-source-group');
          const referenceTray = document.querySelector('#video-reference-tray');
          const explainsEmptyState = emptyState?.textContent.includes('Add an image reference');
          const emptyMedia = {
            hidden: Boolean(emptyState?.hidden),
            sourceGroupHidden: Boolean(sourceGroup?.hidden),
            referenceTrayHidden: Boolean(referenceTray?.hidden),
          };
          studio.addImageReference(saved);
          return {timelineCount, explainsEmptyState: Boolean(explainsEmptyState), emptyMedia};
        }"""
    )
    check(
        "one media empty state replaces two empty lists",
        empty_reference_list
        == {
            "timelineCount": 0,
            "explainsEmptyState": True,
            "emptyMedia": {"hidden": False, "sourceGroupHidden": True, "referenceTrayHidden": True},
        },
        str(empty_reference_list),
    )
    check(
        "video sources stay beside the prompt in the right sidebar",
        page.locator("aside #video-source-panel").count() == 1
        and page.locator(".work #video-source-panel").count() == 0
        and page.locator("#video-timeline").count() == 0,
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
        and page.locator("#video-source-panel .video-reference").nth(2).get_attribute("title") == "shortcut.png",
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
        page.locator("#go-sub").inner_text() == "about 50s",
        page.locator("#go-sub").inner_text(),
    )
    page.locator("label[for=mode-generate]").click()
    switch_workspace(page, "video")
    check(
        "an empty video gallery stays out of the workspace",
        page.locator("#video-gallery").is_hidden(),
    )
    stage_surfaces = page.evaluate(
        """() => {
          const root = document.documentElement;
          const original = root.dataset.theme;
          root.dataset.theme = 'kodak';
          const image = getComputedStyle(document.querySelector('#image-stage')).backgroundColor;
          const video = getComputedStyle(document.querySelector('.video-preview-area')).backgroundColor;
          if (original) root.dataset.theme = original;
          else delete root.dataset.theme;
          return {image, video};
        }"""
    )
    check(
        "Image and Video share the same stage surface in each mode",
        stage_surfaces["image"] == stage_surfaces["video"],
        str(stage_surfaces),
    )
    check(
        "video duration starts at the documented 121-frame example",
        page.locator("#video-duration").input_value() == "121"
        and page.locator("#video-duration-value").inner_text() == "5.0 sec"
        and "121 frames" in page.locator("#video-frame-count").inner_text(),
        page.locator("#video-frame-count").inner_text(),
    )
    page.get_by_role("button", name="Set duration to 15 seconds").click()
    check(
        "15-second preset reaches the 361-frame cap",
        page.locator("#video-duration").input_value() == "361"
        and "361 frames" in page.locator("#video-frame-count").inner_text(),
    )
    page.get_by_role("button", name="Set duration to 5 seconds").click()
    page.fill("#video-prompt", ("A long written shot for the box. " * 30).strip())
    grown = page.evaluate("() => document.getElementById('video-prompt').getBoundingClientRect().height")
    page.fill("#video-prompt", "short")
    small = page.evaluate("() => document.getElementById('video-prompt').getBoundingClientRect().height")
    check(
        "the focused video prompt stays expanded for long and short text, at the shared cap",
        grown == small == 320,
        f"grown {grown:.0f}px, short {small:.0f}px",
    )
    page.locator("#video-media-upload").set_input_files(
        {"name": "notes.txt", "mimeType": "text/plain", "buffer": b"not an image"}
    )
    page.locator("#toasts .toast.error").last.wait_for(state="visible", timeout=10000)
    check(
        "a file that is neither an image nor a video shows a visible error",
        page.locator("#toasts .toast.error").last.inner_text() == "Choose an image, a video or an audio file.",
        page.locator("#toasts .toast.error").last.inner_text(),
    )

    # Generate takes one audio track, and the run follows it. The door offers the kind, the
    # row shows the track, and a second one is refused rather than replacing it silently.
    page.locator("#video-media-upload").set_input_files(str(AUDIO))
    page.wait_for_function("() => document.querySelectorAll('#video-audios .video-audio').length === 1")
    track = page.evaluate(
        """() => ({
          accept: document.getElementById('video-media-upload').accept,
          name: document.querySelector('#video-audios .video-audio-name').textContent,
          trayShown: !document.getElementById('video-audio-tray').hidden,
          emptyHidden: document.getElementById('video-media-empty').hidden,
          removable: Boolean(document.querySelector('#video-audios [data-action=remove-audio]')),
        })"""
    )
    check(
        "generate takes an audio track and shows it as a row",
        track["accept"] == ".png,.jpg,.jpeg,.webp,.gif,.wav,.mp3,.flac,.ogg,.oga,.m4a,.aac,.aif,.aiff"
        and track["name"] == "theme.wav"
        and track["trayShown"]
        and track["emptyHidden"]
        and track["removable"],
        json.dumps(track),
    )
    page.locator("#video-media-upload").set_input_files(str(AUDIO))
    page.locator("#toasts .toast.error").last.wait_for(state="visible", timeout=10000)
    check(
        "the same track twice is refused",
        page.locator("#toasts .toast.error").last.inner_text() == "That track is already here."
        and page.locator("#video-audios .video-audio").count() == 1,
        page.locator("#toasts .toast.error").last.inner_text(),
    )
    page.evaluate("() => document.querySelector('#video-modes input[value=edit]').click()")
    hidden_in_edit = page.locator("#video-audio-tray").is_hidden()
    page.evaluate("() => document.querySelector('#video-modes input[value=generate]').click()")
    check(
        "the track belongs to generate, and edit hides its tray",
        hidden_in_edit
        and page.locator("#video-audio-tray").is_visible()
        and page.locator("#video-audios .video-audio").count() == 1,
        f"hidden in edit: {hidden_in_edit}",
    )

    # The Look rows are the mode's. Generate carries them and an edit's prompt is the
    # effect's own words, so the section stays away there.
    check(
        "generate carries the video Look rows and edit puts them away",
        hidden_in_edit
        and page.locator("#video-look").is_visible()
        and page.evaluate(
            """() => [...document.querySelectorAll('#video-look-rows .look-row-toggle .label')]
                 .map(label => label.textContent)"""
        )
        == ["Light", "Atmosphere", "Grade", "Mix"],
        page.locator("#video-look-rows").inner_text()[:120].replace("\n", " "),
    )
    page.locator("#video-look summary").click()
    page.locator("#video-look-rows .look-row-toggle").first.click()
    page.get_by_role("button", name="Golden hour").click()
    look_added = page.evaluate(
        """() => ({
          values: document.getElementById('video-look-values').textContent,
          tail: document.getElementById('video-look-adds').textContent,
          hidden: document.getElementById('video-look-adds').hidden,
        })"""
    )
    check(
        "a video Look pick appends its sentence under the prompt",
        look_added["values"] == "Golden hour"
        and "Warm low sun from the side, long shadows." in look_added["tail"]
        and not look_added["hidden"],
        json.dumps(look_added),
    )
    page.locator("#video-look-adds .chip").first.click()
    check(
        "a second click takes the video Look pick back off",
        page.evaluate(
            """() => ({
              values: document.getElementById('video-look-values').textContent,
              hidden: document.getElementById('video-look-adds').hidden,
            })"""
        )
        == {"values": "none", "hidden": True},
        page.locator("#video-look-values").inner_text(),
    )
    page.locator("#video-look summary").click()
    page.evaluate("() => document.querySelector('#video-modes input[value=edit]').click()")
    look_hidden_in_edit = page.locator("#video-look").is_hidden()
    page.evaluate("() => document.querySelector('#video-modes input[value=generate]').click()")
    check(
        "the video Look section is hidden in edit",
        look_hidden_in_edit,
        f"hidden in edit: {look_hidden_in_edit}",
    )

    # A clip is an edit input now, so the paste, the source row, the player and the capture all
    # run in Edit. Generate keeps images.
    page.evaluate("() => document.querySelector('#video-modes input[value=edit]').click()")
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
    page.locator("#video-media-upload").set_input_files(
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
    # An added clip shows its own first frame, and the row's highlight covers its delete
    # button. That button sits in a column beside the select, so the colour has to be on
    # the row. The first frame is a canvas seek, so it lands a moment after the list draws.
    page.wait_for_function(
        "() => { const picture = document.querySelector('.video-source-item .video-source-thumb img');"
        "return picture && picture.complete && picture.naturalWidth > 0; }",
        timeout=30000,
    )
    source_row = page.evaluate(
        """() => {
          const row = document.querySelector('.video-source-item');
          const select = row.querySelector('.video-source');
          const remove = row.querySelector('.video-source-remove');
          const rowBox = row.getBoundingClientRect();
          const removeBox = remove.getBoundingClientRect();
          return {
            selected: row.classList.contains('selected'),
            rowBackground: getComputedStyle(row).backgroundColor,
            selectBackground: getComputedStyle(select).backgroundColor,
            removeInsideRow: removeBox.left >= rowBox.left && removeBox.right <= rowBox.right + 1,
          };
        }"""
    )
    check(
        "an added video shows its own frame and the highlight covers its delete button",
        source_row.get("selected")
        and source_row.get("rowBackground") != "rgba(0, 0, 0, 0)"
        and source_row.get("selectBackground") == "rgba(0, 0, 0, 0)"
        and source_row.get("removeInsideRow"),
        str(source_row),
    )
    check(
        "imported video files stay in source assets without a timeline",
        page.locator("#video-source-list .video-source").count() == 1
        and page.locator("#video-gallery .video-clip").count() == 0
        and page.locator("#video-timeline").count() == 0,
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
        and page.locator("#video-timeline").count() == 0,
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
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Add this frame as a reference").click()
    page.wait_for_function("() => document.querySelectorAll('#video-source-panel .video-reference').length === 2")
    captured_frame_index = page.evaluate("() => document.getElementById('video-studio').imageReferences[1].frameIndex")
    check(
        "captured pixels and frame metadata use the same source time",
        captured_frame_index == expected_capture["frame"]
        and page.locator("#video-source-panel .video-reference").nth(1).get_attribute("title")
        == expected_capture["name"],
        f"expected {expected_capture}, got frame {captured_frame_index}",
    )
    check(
        "the player action adds a source frame at its output time",
        captured_frame_index == expected_capture["frame"]
        and page.locator("#video-source-panel .video-reference").nth(1).get_attribute("title")
        == expected_capture["name"],
        f"frame {captured_frame_index}",
    )
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Use current frame in Image").click()
    page.wait_for_function("() => document.querySelector('#media-image-mode').getAttribute('aria-pressed') === 'true'")
    page.locator("#thumbs img[alt^='demo.webm frame']").wait_for(state="visible", timeout=10000)
    check(
        "the player frame action becomes an image reference",
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
        and page.locator("#video-source-list .video-source").count() == 0
        and page.locator("#video-source-panel .video-reference").count() == 3
        and page.evaluate("() => (document.querySelector('#video-modes input:checked') || {}).value") == "generate"
        and "did not load as a video reference" not in page.locator("#toasts").inner_text(),
        f"video mode: {page.locator('#media-video-mode').get_attribute('aria-pressed')}, "
        f"strip hidden: {page.locator('#strip-wrap').is_hidden()}, "
        f"output clips: {page.locator('#video-gallery .video-clip').count()}, "
        f"video references: {page.locator('#video-source-panel .video-reference').count()}, "
        f"names: {page.locator('#video-source-panel .video-reference').evaluate_all('nodes => nodes.map(node => node.title)')}, "
        f"state: {page.locator('#video-studio').evaluate('element => element.imageReferences.map(item => item.name)')}, "
        f"toast: {page.locator('#toasts').inner_text()}",
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
        and page.locator("#video-duration-value").inner_text() == "10.0 sec"
        and "384 × 640" in summary  # noqa: RUF001
        and "241 frames" in summary,
        summary,
    )
    sent_frame = page.evaluate("() => document.getElementById('video-studio').imageReferences[1].frameIndex")
    check(
        "captured source time remains inside the selected video duration",
        0 <= sent_frame < 241,
        f"frame {sent_frame} of 240",
    )
    page.locator("#video-advanced summary").click()
    page.fill("#video-seed", "4294967296")
    page.locator("#video-generate").click()
    page.wait_for_function(
        "() => document.querySelector('#video-request-status').textContent === 'Video generation failed.'",
        timeout=10000,
    )
    check(
        "out-of-range video seeds are stopped before the request",
        len(video_posts) == 0
        and page.locator("#toasts .toast.error").last.inner_text()
        == "Seed must be a whole number from 0 to 4294967295.",
        page.locator("#toasts .toast.error").last.inner_text(),
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
    page.locator("#video-generate").click()
    page.locator("body.video-busy").wait_for(state="attached", timeout=10000)
    starting_locked = page.evaluate(
        """() => ({
          disabled: document.querySelector('#video-generate').disabled,
          label: document.querySelector('#video-generate').innerText,
          panelHeld: document.querySelector('#form').dataset.panelHeld === 'true',
          durationPointerLocked: document.querySelector('#video-duration').style.pointerEvents === 'none',
          controlsOpacity: getComputedStyle(document.querySelector('.controls')).opacity,
          statusVisuallyHidden: document.querySelector('#video-request-status').classList.contains('visually-hidden'),
        })"""
    )
    check(
        "video shows one status and a visible lock while cancel waits for the server",
        starting_locked["disabled"]
        and starting_locked["label"] == "Cancel"
        and starting_locked["panelHeld"]
        and starting_locked["durationPointerLocked"]
        and float(starting_locked["controlsOpacity"]) < 1
        and starting_locked["statusVisuallyHidden"],
        str(starting_locked),
    )
    page.evaluate("() => { window.__studioProgressReady = true; }")
    page.evaluate("() => { window.__studioForeignRequestId = 'another-tab'; }")
    page.wait_for_timeout(500)
    foreign_run_state = page.evaluate(
        """() => ({
          disabled: document.querySelector('#video-generate').disabled,
          label: document.querySelector('#video-generate').innerText,
        })"""
    )
    check(
        "another tab cannot unlock this request's cancel button",
        foreign_run_state["disabled"] and foreign_run_state["label"] == "Cancel",
        str(foreign_run_state),
    )
    page.evaluate("() => { window.__studioForeignRequestId = null; }")
    page.get_by_role("button", name="Cancel", exact=True).wait_for(state="visible", timeout=10000)
    page.wait_for_function(
        "() => !document.querySelector('#video-generate').disabled",
        timeout=10000,
    )
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
    page.get_by_role("button", name="Cancel", exact=True).click()
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
          panelReleased: document.querySelector('#form').dataset.panelHeld !== 'true',
        })"""
    )
    check(
        "cancel stops the request, keeps inputs, and removes the pending gallery tile",
        cancel_retained["requested"]
        and cancel_retained["prompt"]
        and cancel_retained["references"] == 3
        and cancel_retained["pending"] == 0
        and cancel_retained["released"]
        and cancel_retained["panelReleased"],
        str(cancel_retained),
    )
    page.evaluate("() => { window.fetch = window.__studioOriginalFetch; }")
    page.fill("#video-seed", "")
    duration_reference = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          const reference = studio.imageReferences.at(-1);
          const duration = document.getElementById('video-duration');
          reference.frameIndex = Number(duration.value) + 40;
          duration.dispatchEvent(new Event('input', {bubbles: true}));
          return {frameIndex: studio.imageReferences.at(-1).frameIndex,
            lastFrame: Number(duration.value) - 1};
        }"""
    )
    check(
        "shortening duration keeps keyframe references inside the output",
        duration_reference["frameIndex"] == duration_reference["lastFrame"] == 240,
        str(duration_reference),
    )
    check(
        "duration change explains when a reference moves to the last frame",
        "moved to frame 241" in page.locator("#toasts").inner_text(),
        page.locator("#toasts").inner_text(),
    )
    sent_strength = page.locator("#video-studio").evaluate("element => element.imageReferences[1].strength")
    page.locator("#video-generate").click()
    page.wait_for_function(
        "() => ['Stub response added. No video file was generated.', 'Video generation failed.']"
        ".includes(document.querySelector('#video-request-status').textContent)",
        timeout=30000,
    )
    request_status = page.locator("#video-request-status").inner_text()
    check(
        "stub video generation completes without a media file",
        request_status == "Stub response added. No video file was generated.",
        request_status + ": " + page.locator("#toasts").inner_text(),
    )
    request = video_posts[-1] if video_posts else {}
    check(
        "video generation sends selected settings and shared references",
        request.get("num_frames") == 241
        and request.get("width") == 384
        and request.get("height") == 640
        and len(request.get("references", [])) == 3
        and request.get("seed") is None
        and isinstance(request.get("request_id"), str)
        and len(request.get("request_id", "")) >= 16
        and request["references"][1].get("frame_index") == sent_frame == captured_frame_index
        and request["references"][1].get("strength") == sent_strength == 1
        and all(
            0 <= reference.get("frame_index", -1) < request.get("num_frames", 0)
            for reference in request.get("references", [])
        )
        and all(len(reference.get("image", "")) > 100 for reference in request.get("references", [])),
        json.dumps({key: value for key, value in request.items() if key != "references"})
        + f", references: {len(request.get('references', []))}",
    )
    run_meta = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          const clip = studio.clips.find((one) => one.kind === 'generated');
          return clip ? {mode: clip.metadata.mode, precision: clip.metadata.precision,
                         model: clip.metadata.modelName, effect: clip.metadata.effect} : null;
        }"""
    )
    check(
        "a clip records its model, precision, mode and effect",
        run_meta is not None
        and run_meta["mode"] == "generate"
        and run_meta["precision"] == "int8"
        and run_meta["model"] == "LTX-2.5"
        and run_meta["effect"] == "",
        json.dumps(run_meta),
    )
    check(
        "stub video output enters the video gallery without fake media bytes",
        page.locator("#video-gallery .video-clip").count() == 1
        # Generate offers no clip, by design: the clip is Edit's input.
        and page.locator("#video-source-list .video-source").count() == 0
        and page.get_by_text("The stub returns metadata only.").is_visible(),
        f"video clips: {page.locator('#video-gallery .video-clip').count()}",
    )
    check(
        "a successful video run clears its prompt and image references",
        page.locator("#video-prompt").input_value() == ""
        and page.locator("#video-generate").is_disabled()
        and page.locator("#video-source-panel .video-reference").count() == 0
        and page.locator("#video-reference-count").text_content() == "0 images"
        and page.locator("#video-source-list .video-source").count() == 0
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
        and "384 \u00d7 640" in page.locator("#video-output-details").inner_text()
        and re.search(r"241 frames", page.locator("#video-output-details").inner_text()) is not None
        and seed_match is not None
        and 0 <= int(seed_match.group(1)) <= 4294967295
        and "3 image references" in page.locator("#video-output-details").inner_text()
        and "Request time" in page.locator("#video-output-details").inner_text()
        and page.locator("#video-output-details.stage-bar .prompt-line").count() == 1
        and page.locator("#video-output-details .facts").count() == 1
        and page.locator("#video-output-details .actions").count() == 1
        and "A kite rises as the camera pans across the shore" not in stub_details,
        page.locator("#video-output-details").inner_text(),
    )
    page.locator("#video-output-details .video-output-prompt").click()
    short_prompt_state = page.evaluate(
        """() => {
          const prompt = document.querySelector('#video-output-details .video-output-prompt');
          return {tag: prompt.tagName, role: prompt.getAttribute('role'),
            tabIndex: prompt.getAttribute('tabindex'), sheetOpen: Boolean(document.querySelector('#video-prompt-sheet'))};
        }"""
    )
    check(
        "a short video prompt stays plain text and does not open a sheet",
        short_prompt_state == {"tag": "P", "role": None, "tabIndex": None, "sheetOpen": False},
        str(short_prompt_state),
    )
    page.evaluate("() => document.getElementById('video-studio').closeOutputPromptSheet(false)")
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
    page.locator("#video-output-details .video-output-prompt[role=button]").focus()
    page.keyboard.press("Enter")
    prompt_sheet = page.locator("#video-prompt-sheet")
    prompt_sheet.wait_for(state="visible")
    full_prompt = ("A detailed scene description " * 18).strip()
    check(
        "keyboard opens the complete video prompt over the preview",
        full_prompt in prompt_sheet.inner_text()
        and page.locator("#video-prompt-sheet").get_attribute("aria-label") == "The whole prompt"
        and page.locator("#video-prompt-sheet dl dt").inner_text() == "Prompt"
        and page.locator("#video-prompt-sheet dl dd").inner_text() == full_prompt
        and page.locator(".video-output-prompt").get_attribute("aria-controls") == "video-prompt-sheet"
        and page.evaluate("() => document.activeElement?.getAttribute('aria-label')") == "Close",
        json.dumps(
            {
                "sheet": prompt_sheet.inner_text(),
                "label": prompt_sheet.get_attribute("aria-label"),
                "term": page.locator("#video-prompt-sheet dl dt").inner_text(),
                "value": page.locator("#video-prompt-sheet dl dd").inner_text(),
                "controls": page.locator(".video-output-prompt").get_attribute("aria-controls"),
                "focus": page.evaluate("() => document.activeElement?.getAttribute('aria-label')"),
            }
        ),
    )
    # The source row lives in Edit now: the switch goes there for this pair, then back to
    # Generate, which the checks below read.
    page.evaluate("() => document.querySelector('#video-modes input[value=edit]').click()")
    page.locator("#video-source-list .video-source").first.click()
    check(
        "selecting another clip closes the old prompt sheet",
        page.locator("#video-prompt-sheet").count() == 0
        and "demo.webm" in page.locator("#video-output-details").inner_text(),
    )
    page.evaluate("() => document.querySelector('#video-modes input[value=generate]').click()")
    page.locator("#video-gallery .video-clip").first.click()
    page.locator("#video-output-details .video-output-prompt[role=button]").focus()
    page.keyboard.press("Enter")
    check(
        "the selected clip can open its own prompt sheet",
        full_prompt in page.locator("#video-prompt-sheet").inner_text(),
        json.dumps(
            {
                "sheet": page.locator("#video-prompt-sheet").inner_text(),
                "prompt": page.locator(".video-output-prompt").inner_text(),
                "role": page.locator(".video-output-prompt").get_attribute("role"),
            }
        ),
    )
    page.keyboard.press("Escape")
    check(
        "Escape closes the full prompt and restores caption focus",
        page.locator("#video-prompt-sheet").count() == 0
        and page.evaluate("() => document.activeElement?.matches('.video-output-prompt[role=button]')"),
    )
    resize_prompt = ("A detailed scene description " * 10).strip()
    page.evaluate(
        """prompt => {
          const studio = document.getElementById('video-studio');
          studio.selectedClip().metadata.prompt = prompt;
          studio.renderOutputDetails();
        }""",
        resize_prompt,
    )
    page.wait_for_function(
        "() => document.querySelector('.video-output-prompt')?.getAttribute('role') === 'button'",
        timeout=10000,
    )
    page.set_viewport_size({"width": 2560, "height": 1000})
    page.wait_for_function(
        "() => !document.querySelector('.video-output-prompt')?.hasAttribute('role')",
        timeout=10000,
    )
    page.locator("#video-output-details .video-output-prompt").click()
    check(
        "a prompt stops acting as a control when the full text fits",
        page.locator(".video-output-prompt").get_attribute("role") is None
        and page.locator("#video-prompt-sheet").count() == 0,
    )
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.wait_for_function(
        "() => document.querySelector('.video-output-prompt')?.getAttribute('role') === 'button'",
        timeout=10000,
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
              backend: 'ltx25_mlx', modelName: 'LTX-2.5',
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
    generated_card = page.locator("#video-gallery .video-gallery-item").nth(0)
    generated_details = page.locator("#video-output-details").inner_text()
    video_presentation = page.evaluate(
        """() => {
          const monitor = document.querySelector('#video-preview-content-root .video-tv-frame');
          const edge = monitor?.querySelector('.video-tv-edge');
          const actions = document.querySelector('#video-output-details .video-output-actions');
          const actionOrder = actions ? Array.from(actions.children).flatMap(item => {
            if (item.classList.contains('rule')) return [];
            const label = item.matches('a, button') ? item.getAttribute('aria-label')
              : item.querySelector('button')?.getAttribute('aria-label');
            return label ? [label] : [];
          }) : [];
          const facts = document.querySelector('#video-output-details .video-output-facts');
          const screen = monitor?.querySelector('.video-tv-screen');
          const details = document.querySelector('#video-output-details');
          const directVideoFrameAction = Boolean(actions?.querySelector('[data-action="capture-video-frame"]'));
          const directEditAction = Boolean(actions?.querySelector('[data-action="edit-this-clip"]'));
          return {
            isMonitorFrame: Boolean(monitor && screen && monitor.querySelector('#video-preview')),
            detailsInStage: Boolean(details?.closest('#video-preview-root')
              && details.classList.contains('stage-bar')),
            model: edge?.querySelector('.video-tv-model')?.textContent,
            serial: edge?.querySelector('.video-tv-serial')?.textContent,
            actionOrder,
            hasActionDivider: Boolean(actions?.querySelector('.rule')),
            facts: facts?.innerText,
            referenceDetailCount: document.querySelectorAll('.video-output-references').length,
            directFrameAction: Boolean(actions?.querySelector('[data-action="capture-image-frame"]')),
            directVideoFrameAction,
            directEditAction,
          };
        }"""
    )
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
          frameToImage: [...document.querySelectorAll('#video-output-menu [role="menuitem"]')]
            .some(item => item.textContent.includes('Use current frame in Image')),
          menus: document.querySelectorAll('#video-output-menu').length,
          menuItems: document.querySelectorAll('#video-output-menu [role="menuitem"]')
            .length,
        })"""
    )
    check(
        "video gallery uses the Image filmstrip scale",
        gallery_geometry["cardWidth"] <= 120
        and gallery_geometry["thumbnailHeight"] <= 65
        and gallery_geometry["galleryHeight"] <= 152
        and page.locator("#video-gallery .video-clips.strip").count() == 1
        and page.locator("#video-gallery .video-clip.frame").count() == 2
        and page.locator("#video-gallery .video-clip-remove").count() == 0,
        str(gallery_geometry),
    )
    gallery_actions = page.evaluate(
        """() => ({
          note: document.querySelector('#video-gallery-note')?.textContent,
          downloadVisible: !document.querySelector('#video-gallery-download').hidden,
          clearVisible: !document.querySelector('#video-gallery-clear').hidden,
          videos: document.querySelectorAll('#video-gallery .video-clip').length,
        })"""
    )
    check(
        "video gallery shows its browser state and bulk actions",
        gallery_actions
        == {
            "note": "2 videos in this tab. Download the ones you want to keep.",
            "downloadVisible": True,
            "clearVisible": True,
            "videos": 2,
        },
        str(gallery_actions),
    )
    # A render in flight owns the screen, and the strip is how the screen is taken back:
    # picking a clip has to show that clip while the run keeps going, which is what the
    # image strip already does with its waiting frame. The state is set the way the
    # page's own poll sets it, because the stub render is over before a click can land.
    pending_state = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          studio.setGenerationProgress(
            {running: true, stage: 'running', step: 3, total: 11, phase: 1, stopping: false}, 12.5,
            {width: 384, height: 384, modelName: 'LTX-2.5'});
          return {
            monitor: Boolean(document.querySelector('.video-render-placeholder')),
            tile: document.querySelector('#video-gallery .video-gallery-pending')?.getAttribute('aria-pressed'),
            selected: document.querySelectorAll('#video-gallery .video-clip[aria-pressed=true]').length,
          };
        }"""
    )
    check(
        "a render in flight owns the screen and names the current entry in the strip",
        pending_state == {"monitor": True, "tile": "true", "selected": 0},
        str(pending_state),
    )
    picked = page.evaluate("""() => document.querySelector('#video-gallery .video-clip').dataset.clipId""")
    page.locator("#video-gallery .video-clip").first.click()
    switched = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          return {
            monitor: Boolean(document.querySelector('.video-render-placeholder')),
            tile: document.querySelector('#video-gallery .video-gallery-pending')?.getAttribute('aria-pressed'),
            selected: document.querySelector('#video-gallery .video-clip[aria-pressed=true]')?.dataset.clipId,
            step: studio.generationProgress?.step,
            clips: document.querySelectorAll('#video-gallery .video-clip').length,
            prompt: document.querySelector('.video-output-prompt')?.textContent,
            expected: studio.selectedClip()?.metadata?.prompt,
          };
        }"""
    )
    check(
        "picking a clip during a render shows that clip and leaves the run alone",
        switched["monitor"] is False
        and switched["tile"] == "false"
        and switched["selected"] == picked
        and switched["step"] == 3
        and switched["clips"] == 2
        and switched["prompt"] == switched["expected"]
        and bool(switched["expected"]),
        json.dumps({**switched, "picked": picked}),
    )
    page.locator("#video-gallery .video-gallery-pending").click()
    back_to_render = page.evaluate(
        """() => ({
          monitor: Boolean(document.querySelector('.video-render-placeholder')),
          tile: document.querySelector('#video-gallery .video-gallery-pending')?.getAttribute('aria-pressed'),
        })"""
    )
    check(
        "the pending tile puts the render back on the screen",
        back_to_render == {"monitor": True, "tile": "true"},
        str(back_to_render),
    )
    page.evaluate("() => document.getElementById('video-studio').setGenerationProgress(null)")
    settled = page.evaluate(
        """() => ({
          monitor: Boolean(document.querySelector('.video-render-placeholder')),
          selected: document.querySelector('#video-gallery .video-clip[aria-pressed=true]')?.dataset.clipId,
        })"""
    )
    check(
        "the render ending leaves the chosen clip on the screen",
        settled == {"monitor": False, "selected": picked},
        str(settled),
    )
    # The strip reads newest first, so the arrows walk that way too: right is the older
    # clip. This starts on the newest, which a render selects, and comes back to it, so
    # the checks below read the clip the run just made.
    page.locator("#video-gallery .video-clip").nth(0).focus()
    page.keyboard.press("ArrowRight")
    previous_clip = page.evaluate(
        """() => ({
          selected: document.querySelector('#video-gallery .video-clip[aria-pressed=true]')?.dataset.clipId,
          focused: document.activeElement?.dataset.clipId,
          clips: [...document.querySelectorAll('#video-gallery .video-clip')].map(clip => clip.dataset.clipId),
        })"""
    )
    page.keyboard.press("ArrowRight")
    first_clip_edge = page.evaluate(
        """() => document.querySelector('#video-gallery .video-clip[aria-pressed=true]')?.dataset.clipId"""
    )
    page.keyboard.press("ArrowLeft")
    next_clip = page.evaluate(
        """() => ({
          selected: document.querySelector('#video-gallery .video-clip[aria-pressed=true]')?.dataset.clipId,
          focused: document.activeElement?.dataset.clipId,
        })"""
    )
    check(
        "Video gallery arrows select adjacent clips and keep focus",
        len(previous_clip["clips"]) == 2
        and previous_clip["selected"] == previous_clip["clips"][1]
        and previous_clip["focused"] == previous_clip["clips"][1]
        and first_clip_edge == previous_clip["clips"][1]
        and next_clip["selected"] == previous_clip["clips"][0]
        and next_clip["focused"] == previous_clip["clips"][0],
        json.dumps({"previous": previous_clip, "edge": first_clip_edge, "next": next_clip}),
    )
    check(
        "generated gallery thumbnail and output metadata appear with the clip",
        thumbnail_ready
        and generated_card.locator(".video-clip-thumb img").count() == 1
        and "96 \u00d7 64" in generated_details
        and re.search(r"12 frames", generated_details) is not None
        and re.search(r"Seed\s+7", generated_details) is not None
        and "2 image references" in generated_details
        and "Took 01:23.2" in generated_details
        and "01:23.2" in generated_details
        and "An amber kite crosses a blue sky" in generated_details
        and "start.png" not in generated_details
        and "end.png" not in generated_details
        and "Generated" not in generated_details
        and "LTX-2.5" not in (video_presentation.get("facts") or "")
        and video_presentation.get("isMonitorFrame")
        and video_presentation.get("detailsInStage")
        and video_presentation.get("model") == "LTX-2.5"
        and video_presentation.get("serial") == "02"
        and video_presentation.get("referenceDetailCount") == 0
        and video_presentation.get("directFrameAction") is False
        and video_presentation.get("actionOrder")
        == [
            "Add reference",
            "More actions",
            "Download video",
            "Remove video LTX-2.5 1s",
            "Full screen",
        ]
        and video_presentation.get("hasActionDivider")
        and video_presentation.get("directVideoFrameAction")
        and page.locator("#video-output-details .video-output-actions a[download]").count() == 1
        # The download describes the prompt and preserves its actual format.
        and re.fullmatch(
            r"video-.+-\d{8}-\d{9}-[a-z0-9]+\.webm",
            page.locator("#video-output-details .video-output-actions a[download]").get_attribute("download"),
        )
        is not None
        and page.locator("#video-output-details .video-output-actions [aria-label='More actions']").count() == 1
        and page.get_by_role("button", name="Remove video LTX-2.5 1s").is_visible()
        and page.get_by_role("button", name="Full screen").is_visible()
        and page.locator("#video-gallery .video-gallery-head").count() == 1
        and page.locator("#video-timeline").count() == 0,
        generated_details
        + "\n"
        + json.dumps(video_presentation)
        + "\n"
        + json.dumps(
            {
                **output_actions,
                "thumbnailReady": thumbnail_ready,
                "thumbnailCount": generated_card.locator(".video-clip-thumb img").count(),
            }
        ),
    )
    thumbnail_color = generated_card.locator(".video-clip-thumb img").evaluate(
        """image => {
          const canvas = document.createElement('canvas');
          canvas.width = image.naturalWidth;
          canvas.height = image.naturalHeight;
          const context = canvas.getContext('2d');
          context.drawImage(image, 0, 0);
          const pixel = context.getImageData(
            Math.floor(canvas.width / 2), Math.floor(canvas.height / 2), 1, 1
          ).data;
          return {red: pixel[0], blue: pixel[2]};
        }"""
    )
    check(
        "video gallery thumbnail shows a representative middle frame",
        thumbnail_color["blue"] > thumbnail_color["red"] + 30,
        str(thumbnail_color),
    )
    video_gallery_box = page.locator("#video-gallery").bounding_box()
    switch_workspace(page, "image")
    image_gallery_box = page.locator("#strip-wrap").bounding_box()
    switch_workspace(page, "video")
    check(
        "video gallery matches the image gallery width and height",
        video_gallery_box is not None
        and image_gallery_box is not None
        and abs(video_gallery_box["x"] - image_gallery_box["x"]) < 1
        and abs(video_gallery_box["width"] - image_gallery_box["width"]) < 1
        and abs(video_gallery_box["height"] - image_gallery_box["height"]) < 1,
        f"Image: {image_gallery_box}, Video: {video_gallery_box}",
    )
    page.get_by_role("button", name="More actions").click()
    check(
        "video more actions match the image action menu",
        page.get_by_role("menuitem", name="Reuse prompt").is_visible()
        and page.get_by_role("menuitem", name="Reuse seed 7").is_visible()
        and page.get_by_role("menuitem", name="Use current frame in Image").is_visible()
        and page.get_by_role("menuitem", name="Edit this clip").is_visible()
        and page.get_by_role("button", name="Add reference").is_visible()
        and page.get_by_role("menuitem", name="Add reference").count() == 0
        and page.get_by_role("menuitem", name="Remove video LTX-2.5 1s").count() == 0,
        page.locator("#video-output-menu").inner_text(),
    )
    # The menu sends the clip itself to Edit: it is in hand, and the mode switches, so the next
    # press is an effect pick rather than a hunt through the strip.
    page.get_by_role("menuitem", name="Edit this clip").click()
    sent_to_edit = page.evaluate(
        """() => ({
          mode: (document.querySelector('#video-modes input:checked') || {}).value,
          reason: document.getElementById('video-go-sub').textContent,
          selected: document.querySelectorAll('#video-gallery .video-clip.selected').length,
          slot: [...document.querySelectorAll('#video-source-list .video-source-name')].map(name => name.textContent),
          target: document.getElementById('video-studio').editTargetId,
          newest: (() => {
            const clips = document.getElementById('video-studio').clips;
            const newest = clips.filter((clip) => clip.kind === 'generated').slice(-1)[0];
            return newest ? newest.id : '';
          })(),
          // Visible, not merely present: the row was drawn into a group the empty state then
          // hid, and a DOM count called that a pass.
          slotVisible: !document.getElementById('video-source-group').hidden,
          emptyHidden: document.getElementById('video-media-empty').hidden,
        })"""
    )
    check(
        "the output menu sends this clip to Edit, and the slot shows it",
        sent_to_edit["mode"] == "edit"
        and sent_to_edit["reason"] == "Pick an effect"
        and sent_to_edit["selected"] == 1
        and len(sent_to_edit["slot"]) == 1
        and sent_to_edit["slot"][0]
        and sent_to_edit["target"] == sent_to_edit["newest"]
        and sent_to_edit["slotVisible"]
        and sent_to_edit["emptyHidden"],
        json.dumps(sent_to_edit),
    )
    page.evaluate("() => document.querySelector('#video-modes input[value=generate]').click()")
    page.get_by_role("button", name="More actions").click()
    fullscreen_entered = False
    page.get_by_role("button", name="Full screen").click()
    fullscreen_exit = page.get_by_role("button", name="Exit full screen")
    try:
        fullscreen_exit.wait_for(state="visible", timeout=10000)
        fullscreen_entered = page.evaluate(
            """() => {
              const studio = document.querySelector('#video-studio');
              const bounds = studio.getBoundingClientRect();
              return document.fullscreenElement === studio
                && Math.abs(bounds.width - innerWidth) < 2
                && Math.abs(bounds.height - innerHeight) < 2
                && document.querySelector('#video-studio .video-editing-area').getClientRects().length === 0;
            }"""
        )
        fullscreen_exit.click()
        page.wait_for_function("() => !document.fullscreenElement", timeout=10000)
    except PlaywrightTimeoutError:
        pass
    check(
        "video full screen keeps metadata actions available and returns to the studio",
        fullscreen_entered and page.get_by_role("button", name="Full screen").is_visible(),
    )
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Reuse prompt").click()
    check(
        "video prompt can be reused from its selected output, and the rewrite button hears it",
        page.locator("#video-prompt").input_value() == "An amber kite crosses a blue sky"
        and not page.locator("#video-rewrite-toggle").is_disabled(),
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
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Use current frame in Image").click()
    page.wait_for_function("() => document.querySelector('#media-image-mode').getAttribute('aria-pressed') === 'true'")
    check(
        "the more menu sends the current video frame to Image",
        page.locator("#thumbs img[alt^='LTX-2.5 1s frame']").count() == 1,
    )
    switch_workspace(page, "video")
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
          const pendingTile = document.querySelector('#video-gallery .video-gallery-pending');
          const previewStatusStyle = previewStatus && getComputedStyle(previewStatus);
          const noise = previewStatus && getComputedStyle(previewStatus, '::after');
          const stage = document.querySelector('#video-preview-root');
          const statusBox = previewStatus && previewStatus.getBoundingClientRect();
          const stageBox = stage && stage.getBoundingClientRect();
          const headline = previewStatus?.querySelector('.video-render-content strong')?.textContent;
          const elapsed = document.querySelector('#video-preview-content-root .video-tv-elapsed')?.textContent;
          const result = {
            supported: true,
            preparingText,
            preparingIndeterminate,
            preparingHasNoPercent,
            previewStatus: previewStatus && previewStatus.innerText,
            headline,
            previewModel: document.querySelector('#video-preview-content-root .video-tv-model')?.textContent,
            previewSerial: document.querySelector('#video-preview-content-root .video-tv-serial')?.textContent,
            elapsed,
            noise: noise?.backgroundImage,
            previewPercent: previewProgress && previewProgress.getAttribute('aria-valuenow'),
            previewIndeterminate: Boolean(previewProgress && previewProgress.classList.contains('is-indeterminate')),
            previewFill: previewProgress && previewProgress.style.getPropertyValue('--rendered'),
            previewPercentLabel: previewStatus?.querySelector('.video-render-percent')?.textContent,
            progressName: previewProgress && previewProgress.getAttribute('aria-label'),
            progressText: previewProgress && previewProgress.getAttribute('aria-valuetext'),
            hasPlaybackIcon: Boolean(previewStatus && previewStatus.querySelector('.video-render-mark')),
            hasPhaseLabels: Boolean(previewStatus && previewStatus.querySelector('.video-render-stages')),
            hasBrandLabel: Boolean(previewStatus && previewStatus.querySelector('.video-render-brand')),
            pendingTile: Boolean(pendingTile && pendingTile.innerText.includes('Rendering')),
            pendingGalleryCount: document.querySelectorAll('#video-gallery .video-gallery-pending').length,
            previewReplaced: !preview,
            statusIsThumbnail: Boolean(previewStatusStyle && previewStatusStyle.position !== 'absolute'
              && statusBox && stageBox && statusBox.width > 0 && statusBox.height > 0
              && statusBox.left >= stageBox.left && statusBox.right <= stageBox.right
              && statusBox.top >= stageBox.top && statusBox.bottom <= stageBox.bottom),
            thumbnailRatio: statusBox && statusBox.width / statusBox.height,
          };
          studio.setGenerationProgress({running: true, stage: 'running', step: 11, total: 11, phase: 2}, 7);
          result.finishingHeadline = document.querySelector('#video-render-status strong')?.textContent;
          result.finishingPercent = document.querySelector('#video-render-progress')?.getAttribute('aria-valuenow');
          result.roundedPercent = studio.generationProgressDetails({step: 199, total: 200, elapsedSeconds: 7}).percent;
          studio.setGenerationProgress(null);
          result.previewStatusCleared = !document.querySelector('#video-preview-root #video-render-status');
          result.previewStillVisible = Boolean(document.querySelector('#video-preview')
            && !document.querySelector('#video-preview').hidden);
          return result;
        }"""
    )
    check(
        "video keeps progress below 100 percent until the clip is ready",
        progress_result.get("finishingHeadline") == "Finishing the clip"
        and progress_result.get("finishingPercent") == "99"
        and progress_result.get("roundedPercent") == 99,
        str(progress_result),
    )
    check(
        "video loading uses one clear status and an elapsed timer",
        progress_result.get("preparingText") == "00:05.2 elapsed"
        and progress_result.get("preparingIndeterminate")
        and progress_result.get("preparingHasNoPercent"),
        str(progress_result),
    )
    check(
        "video preview uses a quiet status, grain texture, and player-edge timer",
        progress_result.get("supported")
        and progress_result.get("headline") == "Denoising, step 4 of 8"
        and progress_result.get("elapsed") == "00:06.4 elapsed"
        and "LTX-2.5" in progress_result.get("previewModel", "")
        and progress_result.get("previewSerial") == "03"
        and "Loading LTX-2.5" not in progress_result.get("previewStatus", "")
        and "Upscaling" not in progress_result.get("previewStatus", "")
        and "Stage" not in progress_result.get("previewStatus", "")
        and "Pass" not in progress_result.get("previewStatus", "")
        and progress_result.get("previewPercent") == "50"
        and not progress_result.get("previewIndeterminate")
        and progress_result.get("previewFill") == "50%"
        and progress_result.get("previewPercentLabel") == "50%"
        and progress_result.get("progressName") == "Generating video"
        and progress_result.get("progressText") == "50%, 00:06.4 elapsed"
        and "svg" in progress_result.get("noise", "")
        and not progress_result.get("hasPhaseLabels")
        and not progress_result.get("hasBrandLabel")
        and not progress_result.get("hasPlaybackIcon")
        and progress_result.get("pendingTile")
        and progress_result.get("pendingGalleryCount") == 1
        and progress_result.get("previewReplaced")
        and progress_result.get("statusIsThumbnail")
        and abs(progress_result.get("thumbnailRatio", 0) - 0.8) < 0.02,
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
    check(
        "saved video gallery matches the image gallery count and actions",
        page.locator("#video-gallery-note").inner_text().startswith("1 video, kept in this browser.")
        and page.get_by_role("button", name="Download all").is_visible()
        and page.get_by_role("button", name="Clear all").is_visible(),
        page.locator("#video-gallery-note").inner_text(),
    )
    download_start = len(downloads)
    page.get_by_role("button", name="Download all").click()
    page.wait_for_timeout(1000)
    video_downloads = downloads[download_start:]
    check(
        "Download all saves each video and its useful metadata",
        any(re.fullmatch(r"video-.+-\d{8}-\d{9}-[a-z0-9]+\.webm", name) for name in video_downloads)
        and any(re.fullmatch(r"video-metadata-\d{8}-\d{9}\.json", name) for name in video_downloads),
        str(video_downloads),
    )
    page.get_by_role("button", name="Clear all").click()
    page.wait_for_function("() => document.querySelector('#video-gallery .video-clip') === null", timeout=10000)
    page.reload()
    switch_workspace(page, "video")
    page.wait_for_function("() => document.querySelector('#video-gallery .video-clip') === null", timeout=10000)
    check(
        "Clear all removes every generated video and its saved copy",
        page.locator("#video-gallery .video-clip").count() == 0 and page.locator("#video-gallery").is_hidden(),
    )
    switch_workspace(page, "image")
    check(
        "the image gallery returns with its generated result",
        page.locator("#strip-wrap").is_visible()
        and page.locator("#strip .frame").count() == 1
        and page.locator("#video-studio").is_hidden(),
        f"image frames: {page.locator('#strip .frame').count()}",
    )
    switch_workspace(page, "video")
    # ---- Edit mode: a clip in, the same clip changed ----------------------------
    # The switch and the adapter come from the record, the adapter carries the prompt it
    # answers to and the strength it was measured at, and the run posts the clip it changes.
    # Driven through the stub, so none of this needs a GPU.
    # A clip with real bytes to change: an edit needs one, and the strip may have been
    # cleared earlier in the suite.
    # A clip is Edit's input: the mode comes first, then the upload.
    page.evaluate("() => document.querySelector('#video-modes input[value=edit]').click()")
    page.locator("#video-media-upload").set_input_files(
        {"name": "edit-me.webm", "mimeType": "video/webm", "buffer": make_video(page)}
    )
    page.wait_for_function("() => document.querySelectorAll('#video-source-list .video-source').length >= 1")
    page.evaluate("() => document.querySelector('#video-modes input[value=generate]').click()")
    page.fill("#video-prompt", "")
    check(
        "an empty video generate prompt says what it waits for",
        page.locator("#video-generate").is_disabled()
        and page.locator("#video-go-sub").inner_text() == "Write a prompt",
        page.locator("#video-go-sub").inner_text(),
    )
    page.evaluate("() => document.querySelector('#video-modes input[value=edit]').click()")
    edit_form = page.evaluate(
        """() => {
          const capabilities = videoCapabilities();
          return {
            modes: [...document.querySelectorAll('#video-modes input')]
              .map(input => ({mode: input.value, pressed: String(input.checked)})),
            adapters: (capabilities.adapters || []).map(adapter => adapter.id),
            templatesPill: document.getElementById('video-templates-toggle').hidden,
            // The mode's own words: the box is relabelled, and it says what it wants.
            // innerText, not textContent: both halves of a mode's words are in the markup and
            // the stylesheet shows one, so only the shown half counts.
            promptLabel: document.querySelector('#video-controls .prompt-field label').innerText,
            placeholder: document.getElementById('video-prompt').placeholder,
            // The verb alone: the button's second line is the reason it is off.
            runLabel: document.querySelector('#video-run-labels .main').innerText,
            shapeOffered: !document.getElementById('video-duration').closest('.field').classList.contains('generate-only')
              || getComputedStyle(document.getElementById('video-duration').closest('.field')).display !== 'none',
            adapterRow: document.getElementById('video-adapters-toggle').hidden,
            adapterName: document.getElementById('video-adapter-name').textContent,
            runDisabled: document.getElementById('video-generate').disabled,
            panelHead: document.querySelector('#video-source-panel .video-source-panel-head strong').textContent,
            zone: document.getElementById('video-media-empty').innerText,
          };
        }"""
    )
    check(
        "Edit asks for a clip, offers its effects, and puts the shot templates away",
        [entry["mode"] for entry in edit_form["modes"]] == ["generate", "edit"]
        and edit_form["modes"][1]["pressed"] == "true"
        and edit_form["adapters"]
        == [
            "day-to-night",
            "water-simulation",
            "clean-plate",
            "deblur",
            "decompression",
            "restore",
            "upscale-2x",
        ]
        and edit_form["templatesPill"] is True
        and edit_form["promptLabel"] == "What to change"
        and "pick an effect" in edit_form["placeholder"].lower()
        and edit_form["runLabel"] == "Edit"
        and edit_form["shapeOffered"] is False
        and edit_form["adapterRow"] is False
        and edit_form["adapterName"] == "Effect"
        and edit_form["panelHead"] == "Clip to edit"
        and "Optional" not in edit_form["zone"]
        and edit_form["runDisabled"] is True,
        json.dumps(edit_form),
    )
    # The two workspaces share one <form>. The video mode used to write its class there, so
    # Edit in Video rewrote the image form's words while its own switch said Generate.
    switch_workspace(page, "image")
    image_words = page.evaluate(
        """() => ({
          mode: (document.querySelector('input[name=mode]:checked') || {}).value,
          label: document.querySelector('#image-controls .prompt-field label').innerText,
        })"""
    )
    check(
        "the video mode does not rewrite the image form's words",
        image_words["label"] == ("What to change" if image_words["mode"] == "edit" else "Prompt"),
        json.dumps(image_words),
    )
    switch_workspace(page, "video")
    # An edit takes a clip, not an image reference. The chooser offers video files only, and an
    # image that arrives by drop or paste is refused by the component's one door.
    page.locator("#video-media-upload").set_input_files(str(REFERENCE))
    page.wait_for_timeout(300)
    refused = page.evaluate(
        """() => ({
          accept: document.getElementById('video-media-upload').accept,
          references: document.querySelectorAll('#video-references .video-reference').length,
          zone: document.getElementById('video-media-empty').innerText,
          error: document.getElementById('toasts').innerText,
        })"""
    )
    check(
        "an edit refuses an image and offers video files only",
        refused["accept"] == ".mp4,.m4v,.mov,.webm,.ogv"
        and refused["references"] == 0
        and "Add the clip to edit" in refused["zone"]
        and "Choose a video file" in refused["error"],
        json.dumps(refused),
    )
    # The clip landed earlier, so the form has it in hand already. A click on the row is a
    # choice of which clip, not the thing that tells the form a clip exists.
    in_hand = page.evaluate("() => document.getElementById('video-go-sub').textContent")
    check(
        "a clip that landed is in hand without a second click",
        in_hand == "Pick an effect",
        in_hand,
    )
    page.locator("#video-source-list .video-source").first.click()
    page.locator("#video-media-upload").set_input_files(
        {"name": "second.webm", "mimeType": "video/webm", "buffer": make_video(page)}
    )
    page.wait_for_timeout(300)
    second = page.evaluate(
        """() => ({
          sources: document.querySelectorAll('#video-source-list .video-source').length,
          error: document.getElementById('toasts').innerText,
        })"""
    )
    check(
        "an edit refuses a second clip and names the way out",
        second["sources"] == 1 and "one clip" in second["error"],
        json.dumps(second),
    )
    # A clip and words are two of the three things an edit needs. The adapter is the third:
    # the pipeline is the IC-LoRA one and the controller refuses the request without it, so
    # the button waits here rather than letting the server answer with an error.
    page.fill("#video-prompt", "make it night")
    check(
        "an edit with a clip and words still waits for an effect",
        page.locator("#video-generate").is_disabled()
        and page.locator("#video-go-sub").inner_text() == "Pick an effect",
        page.locator("#video-go-sub").inner_text(),
    )
    page.fill("#video-prompt", "")
    page.locator("#video-adapters-toggle").click()
    page.get_by_role("menuitem", name="Day to night").click()
    adapter_chosen = page.evaluate(
        """() => ({
          prompt: document.getElementById('video-prompt').value,
          label: document.getElementById('video-adapter-name').textContent,
          hint: document.getElementById('video-adapter-hint').textContent,
          runDisabled: document.getElementById('video-generate').disabled,
        })"""
    )
    check(
        "picking an effect seeds the prompt it answers to and wakes the run",
        adapter_chosen["label"] == "Day to night"
        and "Only the lighting changes" in adapter_chosen["prompt"]
        and adapter_chosen["runDisabled"] is False,
        json.dumps(adapter_chosen),
    )
    # A switch to Generate and back keeps the adapter and the words it seeded: the pick is
    # part of what the person set up, and generate simply offers no adapter control.
    page.evaluate("() => document.querySelector('#video-modes input[value=generate]').click()")
    page.evaluate("() => document.querySelector('#video-modes input[value=edit]').click()")
    kept = page.evaluate(
        """() => ({
          label: document.getElementById('video-adapter-name').textContent,
          prompt: document.getElementById('video-prompt').value,
        })"""
    )
    check(
        "a mode switch keeps the chosen effect and the words it seeded",
        kept["label"] == "Day to night" and "Only the lighting changes" in kept["prompt"],
        json.dumps(kept),
    )
    edited = []
    page.on(
        "request",
        lambda request: edited.append(request.post_data or "") if request.url.endswith("/video/generate") else None,
    )
    clips_before = page.locator("#video-gallery .video-clip").count()
    page.click("#video-generate")
    page.wait_for_function(
        "count => document.querySelectorAll('#video-gallery .video-clip').length > count",
        arg=clips_before,
        timeout=60000,
    )
    sent = json.loads(edited[-1]) if edited else {}
    clip_sent = sent.get("clip") or {}
    check(
        "an edit posts the mode, the effect, its strength and the clip itself",
        sent.get("mode") == "edit"
        and sent.get("adapter") == "day-to-night"
        and sent.get("adapter_strength") == 1
        and clip_sent.get("name", "").startswith("edit-me.webm")
        and len(clip_sent.get("data", "")) > 1000,
        json.dumps({key: value for key, value in sent.items() if key != "clip"})
        + f", clip bytes: {len(clip_sent.get('data', ''))}",
    )
    # A stub clip has no media to change, so the run stays asleep and the form says why, the
    # way it waits for words rather than refusing after a press.
    page.evaluate("""() => {
      const studio = document.getElementById('video-studio');
      studio.editThisClip(studio.clips.filter(clip => clip.kind === 'generated').slice(-1)[0].id);
    }""")
    stub_clip = page.evaluate("""() => ({runDisabled: document.getElementById('video-generate').disabled})""")
    check(
        "an edit of a clip with no media leaves the run asleep",
        stub_clip["runDisabled"] is True,
        json.dumps(stub_clip),
    )
    page.evaluate("() => document.querySelector('#video-modes input[value=generate]').click()")

    # The edit run above spent the track the generate checks added: a finished run clears
    # what it used. Attach it again for the run whose payload and record these checks read.
    page.locator("#video-media-upload").set_input_files(str(AUDIO))
    page.wait_for_function("() => document.getElementById('video-studio').audio !== null")
    # Every video run asks the pipeline for the video model's own enhancer, so a clip is drawn
    # from a directed shot even when nobody pressed the rewrite button. The request carries
    # that, and the clip's own record carries the words the run was made from. This is the one
    # check that drives the run button itself: the suite's other video runs place their clips
    # directly, and it runs last because the clip it makes would move every gallery count above.
    sent = []
    page.on(
        "request",
        lambda request: sent.append(request.post_data or "") if request.url.endswith("/video/generate") else None,
    )
    before = page.locator(".video-gallery-item:not(.pending)").count()
    page.fill("#video-prompt", "a cat walking on a wall")
    page.evaluate("() => { document.getElementById('video-look').open = true; }")
    page.locator("#video-look-rows .look-row-toggle").first.click()
    page.get_by_role("button", name="Golden hour").click()
    page.click("#video-generate")
    page.wait_for_function(
        "count => document.querySelectorAll('.video-gallery-item:not(.pending)').length > count",
        arg=before,
        timeout=60000,
    )
    sent_run = json.loads(sent[-1]) if sent else {}
    check(
        "the run is made from the words in the box, the Look after them, and the model's own enhancer",
        sent
        and sent_run["prompt"].startswith("a cat walking on a wall")
        and sent_run["prompt"].endswith("Warm low sun from the side, long shadows.")
        and sent_run["enhance"] is True,
        f"{sent_run.get('prompt')!r}, enhance {sent_run.get('enhance')!r}" if sent else "no run",
    )
    record = page.evaluate(
        """() => {
          const clips = document.getElementById('video-studio').clips || [];
          if (!clips.length) return {};
          return clips[clips.length - 1].metadata;
        }"""
    )
    check(
        "and the clip's own record names those words and the Look",
        record.get("prompt", "").startswith("a cat walking on a wall") and record.get("look") == "Golden hour",
        json.dumps({"prompt": record.get("prompt"), "look": record.get("look")}),
    )
    sent_payload = json.loads(sent[-1]) if sent else {}
    track_sent = sent_payload.get("audio") or {}
    record = page.evaluate(
        """() => {
          const clips = document.getElementById('video-studio').clips || [];
          if (!clips.length) return {};
          const clip = clips[clips.length - 1];
          return {pipeline: clip.metadata.pipeline, audio: clip.metadata.audio};
        }"""
    )
    check(
        "the run follows the track it was given, and its record names the pipeline and the track",
        track_sent.get("name") == "theme.wav"
        and base64.b64decode(track_sent.get("data", "")).startswith(b"RIFF")
        and record.get("pipeline") == "a2vid_two_stage"
        and record.get("audio") == "theme.wav",
        json.dumps({"audioSent": track_sent.get("name"), "bytes": len(track_sent.get("data", "")), **record}),
    )
    check(
        "the run clears the track it used",
        page.evaluate("() => document.getElementById('video-studio').audio") is None
        and page.locator("#video-audios .video-audio").count() == 0
        and page.locator("#video-audio-tray").is_hidden(),
    )
    check("the browser reports no page errors", not errors, str(errors))
    browser.close()

shutil.rmtree(SCRATCH, ignore_errors=True)
failed = [name for name, passed in results if not passed]
print(f"\n{len(results) - len(failed)}/{len(results)} passed", "FAILED: " + ", ".join(failed) if failed else "")
sys.exit(1 if failed else 0)
