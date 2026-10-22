"""Shared gallery UX on a fresh all-backends stub; no GPU or schema changes.

Usage: uv run --with playwright python tests/e2e/verify_gallery_browser.py <port> [screenshot-directory]
Fixtures enter through the existing media owners and are kept by their normal stores.
"""

import base64
import io
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

URL = f"http://127.0.0.1:{sys.argv[1]}"
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else None
if SHOTS:
    SHOTS.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix="gallery-fixture-") as scratch:
    video = Path(scratch) / "clip.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x416080:size=384x384:rate=24",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(video),
        ],
        check=True,
    )
    mp4 = base64.b64encode(video.read_bytes()).decode()
stream = io.BytesIO()
with wave.open(stream, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(24000)
    wav.writeframes(
        b"".join(struct.pack("<h", int(2000 * math.sin(index * 2 * math.pi * 440 / 24000))) for index in range(48000))
    )
audio = base64.b64encode(stream.getvalue()).decode()

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL)
    page.wait_for_function(
        'typeof kept !== "undefined" && Boolean(kept) && Boolean(customElements.get("gallery-browser"))'
    )
    # A real UI batch uses one shared operationId, unlike observer :item identities.
    page.evaluate("""async () => {
      const component = document.createElement('gallery-browser');
      component.workspace = 'image'; document.body.append(component); await component.updateComplete;
      component.remove();
      if (component.isConnected) throw new Error('Gallery component cannot detach normally');
    }""")
    page.locator("#advanced summary").click()
    page.locator("#steps").fill("4")
    page.locator("#steps").dispatch_event("input")
    page.locator("#advanced summary").click()
    page.locator("#prompt").fill("A blue paper kite above a quiet field")
    page.locator("#count-toggle").click()
    page.locator("#count-menu button").nth(1).click()
    page.locator("#go").click()
    native = page.locator("#image-gallery-browser")
    native.locator(".gallery-browse-toggle").click()
    expect(native.get_by_role("button", name="Show generation in progress", exact=True)).to_be_visible()
    page.wait_for_function("!busy() && gallery.length === 2", timeout=60000)
    native.get_by_label("Group batches").check()
    expect(native.get_by_role("button", name="Open batch of 2 results", exact=True)).to_be_visible()
    native.get_by_label("Group batches").uncheck()
    native.locator(".gallery-browse-toggle").click()
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#clear-gallery").click()
    page.wait_for_function("gallery.length === 0")
    print("PASS native UI batch: pending tile and grouping with shared operation identity", flush=True)
    page.evaluate(
        """async ({mp4, audio}) => {
      const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 128;
      const ctx = canvas.getContext('2d');
      const blob = (text, type) => new Blob([Uint8Array.from(atob(text), char => char.charCodeAt(0))], {type});
      const videoBlob = blob(mp4, 'video/mp4'), audioBlob = blob(audio, 'audio/wav');
      await videoGalleryReady;
      const now = Date.now();
      for (let i = 1; i <= 16; i++) {
        ctx.fillStyle = `hsl(${i * 35},65%,60%)`; ctx.fillRect(0, 0, 128, 128);
        const thumb = canvas.toDataURL();
        const operation = i <= 4 ? 'gallery-batch:' + i : 'gallery-single-' + i;
        const prompt = (i % 2 ? 'A blue teapot ' : 'A red apple ') + i;
        const mode = i % 2 ? 'generate' : 'edit', model = i % 3 ? 'Model A' : 'Model B';
        const entry = admit({id: i, number: i, src: thumb, seed: i, at: now + i * 1000,
          width: 128, height: 128, steps: 8, elapsed: 1, position: i <= 4 ? i : '1 image', mode,
          prompt, backend: model, backendId: 'qwen21',
          operationId: i <= 4 ? 'native-image-batch' : operation, sources: []});
        await kept.keep(entry);
        const clip = {id: 'video-operation-' + operation, name: 'Clip ' + i, kind: 'generated',
          url: URL.createObjectURL(videoBlob), objectUrl: true, mp4Blob: videoBlob,
          thumbnailUrl: thumb, thumbnailBlob: await (await fetch(thumb)).blob(), duration: 2,
          createdAt: now + i * 1000, metadata: {prompt, mode, seed: i, modelName: model,
            operationId: operation, width: 384, height: 384, frameRate: 24, numFrames: 48, elapsedSeconds: 1}};
        videoStudio.addClip(clip); await videoStudio.persistVideo(clip);
        await voiceStudio.addAudio(audioBlob, {id: operation, text: prompt, model,
          finished_at: (now + i * 1000) / 1000, seed: i,
          settings: {backend: 'drama3', mode: i % 2 ? 'generate' : 'clone', voice: 'Warm and clear'}});
      }
      showNewest(); await voiceStudio.saved;
    }""",
        {"mp4": mp4, "audio": audio},
    )

    for workspace, name in (("image", "Image"), ("video", "Video"), ("voice", "Voice")):
        page.locator(f"#media-{workspace}-mode").click()
        gallery = page.locator(f'gallery-browser[workspace="{workspace}"]')
        gallery.locator(".gallery-browse-toggle").click()
        expect(gallery.locator(".gallery-card")).to_have_count(16)
        expect(gallery.get_by_label("Group batches")).to_have_count(1)
        expect(gallery.get_by_role("searchbox", name="Search gallery")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        # Search and filters derive solely from the saved prompt/script/model fields.
        gallery.get_by_role("searchbox").fill("red apple")
        expect(gallery.locator(".gallery-card")).to_have_count(8)
        gallery.get_by_role("searchbox").fill("no such scene")
        expect(gallery.get_by_text("No matching results", exact=True)).to_be_visible()
        gallery.get_by_role("button", name="Clear filters", exact=True).click()
        expect(gallery.locator(".gallery-card")).to_have_count(16)
        gallery.get_by_label("Filter by model").select_option("Model B")
        expect(gallery.locator(".gallery-card")).to_have_count(5)
        gallery.get_by_label("Filter by model").select_option("")
        gallery.get_by_label("Filter by mode", exact=True).select_option("generate")
        expect(gallery.locator(".gallery-card")).to_have_count(8)
        gallery.get_by_label("Filter by mode", exact=True).select_option("")
        gallery.get_by_label("Gallery order").select_option("oldest")
        expect(gallery.locator(".gallery-card-pick").first.locator(".no")).to_have_text("01")
        gallery.get_by_label("Gallery order").select_option("newest")
        expect(gallery.locator(".gallery-card-pick").first.locator(".no")).to_have_text("16")
        # Only explicit operation-item IDs form batches.
        gallery.get_by_label("Group batches").check()
        expect(gallery.locator(".gallery-card")).to_have_count(13)
        gallery.get_by_role("button", name="Open batch of 4 results", exact=True).click()
        expect(gallery.locator(".gallery-card")).to_have_count(4)
        gallery.get_by_role("button", name="All results", exact=True).click()
        gallery.get_by_label("Group batches").uncheck()
        # Restored filter controls must agree with their rendered results.
        gallery.get_by_role("searchbox").fill("red apple")
        gallery.get_by_label("Filter by model").select_option("Model B")
        gallery.get_by_label("Gallery order").select_option("oldest")
        page.reload()
        page.locator(f"#media-{workspace}-mode").click()
        gallery = page.locator(f'gallery-browser[workspace="{workspace}"]')
        expect(gallery.get_by_role("searchbox")).to_have_value("red apple")
        expect(gallery.get_by_label("Filter by model")).to_have_value("Model B")
        expect(gallery.get_by_label("Gallery order")).to_have_value("oldest")
        expect(gallery.locator(".gallery-card")).to_have_count(2)
        gallery.get_by_role("searchbox").fill("")
        gallery.get_by_label("Filter by model").select_option("")
        gallery.get_by_label("Gallery order").select_option("newest")
        # Arrow navigation updates one preview and keeps focus on the corresponding card.
        cards = gallery.locator(".gallery-card-pick")
        cards.first.click()
        cards.first.press("ArrowRight")
        expect(cards.nth(1)).to_be_focused()
        expect(cards.nth(1)).to_have_attribute("aria-pressed", "true")
        chosen = cards.nth(1).get_attribute("data-item-id")
        grid = gallery.locator(".gallery-browser-grid")
        grid.evaluate("element => { element.scrollTop = 120; element.dispatchEvent(new Event('scroll')); }")
        saved_scroll = grid.evaluate("element => element.scrollTop")
        # Reload restores view preferences without writing new fields to any media record.
        page.reload()
        page.locator(f"#media-{workspace}-mode").click()
        gallery = page.locator(f'gallery-browser[workspace="{workspace}"]')
        expect(gallery.locator(".gallery-card")).to_have_count(16)
        expect(gallery.locator(f'.gallery-card-pick[data-item-id="{chosen}"]')).to_have_attribute(
            "aria-pressed", "true"
        )
        expect(gallery.get_by_label("Group batches")).to_have_count(1)
        page.wait_for_function(
            """({workspace, top}) => Math.abs(document.querySelector(
          `gallery-browser[workspace=${workspace}] .gallery-browser-grid`).scrollTop - top) < 2""",
            arg={"workspace": workspace, "top": saved_scroll},
        )
        # Playback shortcuts stay scoped; Space on an actual action remains that action.
        if workspace in ("video", "voice"):
            gallery.locator(".gallery-card-pick").first.click()
            page.evaluate("document.activeElement.blur()")
            page.keyboard.press("Space")
            playing = (
                "!document.querySelector('#video-preview').paused"
                if workspace == "video"
                else "document.querySelector('audio-preview').playing"
            )
            page.wait_for_function(playing)
            page.keyboard.press("Space")
            page.wait_for_function("! (" + playing + ")")
            if workspace == "video":
                assert "Playback failed" not in page.evaluate("videoStudio.error")
                error = page.evaluate("""async () => {
                  const video = document.querySelector('#video-preview'), play = video.play;
                  video.play = () => Promise.reject(new DOMException('Paused before playback started', 'AbortError'));
                  try { await videoStudio.togglePlayback(); return videoStudio.error; }
                  finally { video.play = play; }
                }""")
                assert "Playback failed" not in error
        # Bulk download and deletion use existing owner actions and existing cross-tab stores.
        other = context.new_page()
        other.on("pageerror", lambda error: errors.append(str(error)))
        other.goto(URL + "/?workspace=" + workspace)
        other.wait_for_function(
            "workspace => document.querySelector(`gallery-browser[workspace=${workspace}]`)?.items.length === 16",
            arg=workspace,
        )
        gallery.get_by_role("button", name="Select", exact=True).click()
        gallery.get_by_role("button", name="Select all 16", exact=True).click()
        expect(gallery.locator(".gallery-check input:checked")).to_have_count(16)
        gallery.get_by_role("button", name="Deselect", exact=True).click()
        gallery.locator(".gallery-check input").nth(0).check()
        gallery.locator(".gallery-check input").nth(1).check()
        downloads = []

        def handler(download, results=downloads):
            results.append(download.suggested_filename)

        page.on("download", handler)
        gallery.get_by_role("button", name="Download selected", exact=True).click()
        page.wait_for_function(
            "workspace => !document.querySelector(`gallery-browser[workspace=${workspace}]`).working", arg=workspace
        )
        assert len(downloads) >= 2 and len(set(downloads)) == len(downloads), downloads
        page.remove_listener("download", handler)
        page.once("dialog", lambda dialog: dialog.dismiss())
        gallery.get_by_role("button", name="Remove selected", exact=True).click()
        expect(gallery.locator(".gallery-card")).to_have_count(16)
        page.once("dialog", lambda dialog: dialog.accept())
        gallery.get_by_role("button", name="Remove selected", exact=True).click()
        expect(gallery.locator(".gallery-card")).to_have_count(14)
        other.wait_for_function(
            "workspace => document.querySelector(`gallery-browser[workspace=${workspace}]`).items.length === 14",
            arg=workspace,
        )
        other.close()
        gallery.locator(".gallery-check input").first.focus()
        page.keyboard.press("Escape")
        expect(gallery.get_by_role("button", name="Select", exact=True)).to_be_visible()
        if SHOTS:
            page.screenshot(path=str(SHOTS / (workspace + "-grid.png")), animations="disabled")
        gallery.get_by_role("searchbox").press("Escape")
        expect(gallery.locator(".gallery-browser-panel")).to_have_count(0)
        print(
            f"PASS {name}: grid, search, filters, sorting, batches, keys, restoration, bulk actions and two tabs",
            flush=True,
        )

    # Compact strips restore after their images load and their workspace becomes visible.
    page.set_viewport_size({"width": 1000, "height": 900})
    for workspace in ("image", "video", "voice"):
        page.locator(f"#media-{workspace}-mode").click()
        selector = {"image": "#strip", "video": "#video-gallery .strip", "voice": "#voice-gallery .strip"}[workspace]
        strip = page.locator(selector)
        expect(strip.locator(".frame:not(.pending)")).to_have_count(14)
        page.wait_for_function(
            "workspace => !document.querySelector(`gallery-browser[workspace=${workspace}]`).restoreScroll",
            arg=workspace,
        )
        page.wait_for_function(
            'selector => Array.from(document.querySelector(selector).querySelectorAll("img")).every(image => image.complete)',
            arg=selector,
        )
        target = strip.evaluate("element => { element.scrollLeft = 150; return element.scrollLeft; }")
        assert target > 0, workspace
        page.wait_for_function(
            '({workspace, target}) => JSON.parse(sessionStorage.getItem("studio-gallery-view-" + workspace) || "{}").stripScroll === target',
            arg={"workspace": workspace, "target": target},
        )
        page.reload()
        page.locator(f"#media-{workspace}-mode").click()
        page.wait_for_function(
            "({selector, target}) => Math.abs(document.querySelector(selector).scrollLeft - target) < 2",
            arg={"selector": selector, "target": target},
        )
    print("PASS compact scroll restoration waits for media and workspace visibility", flush=True)
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#theme-toggle").click()
    page.get_by_role("menuitemcheckbox", name="Keep in this browser", exact=True).click()
    page.wait_for_function(
        '["image", "video", "voice"].every(kind => !sessionStorage.getItem("studio-gallery-view-" + kind))'
    )
    print("PASS Keep off clears gallery view preferences", flush=True)
    # Storage refusal must not prevent any browsing operation.
    page.evaluate(
        "Object.defineProperty(window, 'sessionStorage', {get() {throw new Error('storage denied')}, configurable: true})"
    )
    gallery.locator(".gallery-browse-toggle").click()
    gallery.get_by_role("searchbox").fill("apple")
    assert gallery.locator(".gallery-card").count() > 0
    assert not errors, errors
    print("PASS unavailable presentation storage is non-fatal; no page errors", flush=True)
    browser.close()
