"""Check video edit inputs without GPU work.

uv run studio --stub --all-backends --port <port>
uv run --with playwright python tests/e2e/verify_edit_selection.py <port>
"""

import sys

from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page()
    page.goto(f"http://127.0.0.1:{sys.argv[1]}/?workspace=video")
    page.wait_for_function("() => Boolean(document.getElementById('video-studio').galleryStore)")
    page.evaluate(
        """async () => {
          const canvas = document.createElement('canvas');
          canvas.width = 96;
          canvas.height = 64;
          const stream = canvas.captureStream(12);
          const recorder = new MediaRecorder(stream, {mimeType: 'video/webm'});
          const chunks = [];
          recorder.ondataavailable = event => chunks.push(event.data);
          const stopped = new Promise(resolve => { recorder.onstop = resolve; });
          recorder.start();
          canvas.getContext('2d').fillRect(0, 0, 96, 64);
          await new Promise(resolve => setTimeout(resolve, 300));
          recorder.stop();
          await stopped;
          stream.getTracks().forEach(track => track.stop());
          window.editSelectionBlob = new Blob(chunks, {type: 'video/webm'});
          const studio = document.getElementById('video-studio');
          for (const seed of [7, 8]) {
            await studio.addGeneratedClip(window.editSelectionBlob, {
              modelName: 'LTX-2.5', prompt: 'a room', width: 96, height: 64,
              numFrames: 24, frameRate: 24, duration: 1, seed,
            });
          }
        }"""
    )
    page.locator("#video-gallery .video-clip").first.click()
    page.locator('label[for="video-mode-edit"]').click()
    assert page.evaluate("() => document.getElementById('video-studio').editTargetId") is None
    assert page.locator("#video-source-list .video-source").count() == 0
    print("PASS gallery preview does not become an edit input", flush=True)

    target = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          const target = studio.clips[0];
          studio.editThisClip(target.id);
          return target.id;
        }"""
    )
    page.wait_for_function("() => document.querySelector('#video-preview').videoWidth > 0")
    page.locator("#video-gallery .video-clip").first.click()
    assert page.evaluate("() => document.getElementById('video-studio').editTargetId") == target
    print("PASS another preview preserves the explicit edit input", flush=True)

    page.locator("#video-adapters-toggle").click()
    page.get_by_role("menuitem", name="Day to night").click()
    geometry = page.evaluate(
        """targetId => {
          const target = document.getElementById('video-studio').clips.find(clip => clip.id === targetId);
          target.width = 64;
          target.height = 96;
          return editGeometry();
        }""",
        target,
    )
    assert geometry["height"] > geometry["width"]
    print("PASS edit geometry follows its target while another clip is in the preview", flush=True)

    before = page.evaluate(
        """() => {
          const studio = document.getElementById('video-studio');
          return {ids: studio.clips.map(clip => clip.id), preview: studio.selectedClipId,
            url: studio.clips.find(clip => clip.id === studio.editTargetId).url};
        }"""
    )
    page.locator("#video-source-list .video-source-remove").click()
    page.wait_for_function("() => document.getElementById('video-studio').editTargetId === null")
    after = page.evaluate(
        """async url => {
          const studio = document.getElementById('video-studio');
          return {ids: studio.clips.map(clip => clip.id), preview: studio.selectedClipId,
            bytes: (await (await fetch(url)).blob()).size};
        }""",
        before["url"],
    )
    assert before["ids"] == after["ids"] and before["preview"] == after["preview"]
    assert after["bytes"] > 0
    assert page.locator("#video-go-sub").inner_text() == "Add a clip to edit"
    persisted = page.evaluate(
        """targetId => new Promise((resolve, reject) => {
          const opened = indexedDB.open('studio-video-gallery', 1);
          opened.onerror = () => reject(opened.error);
          opened.onsuccess = () => {
            const request = opened.result.transaction('clips').objectStore('clips').get(targetId);
            request.onsuccess = () => resolve(Boolean(request.result?.mp4?.size));
            request.onerror = () => reject(request.error);
          };
        })""",
        target,
    )
    assert persisted
    print("PASS clearing an edit input preserves the gallery and its media", flush=True)

    for name in ["first.webm", "second.webm"]:
        page.evaluate(
            """name => document.getElementById('video-studio').addVideoFiles([
              new File([window.editSelectionBlob], name, {type: 'video/webm'})])""",
            name,
        )
        page.wait_for_function("() => document.querySelectorAll('#video-source-list .video-source').length === 1")
        page.locator("#video-source-list .video-source-remove").click()
        page.wait_for_function("() => document.getElementById('video-studio').editTargetId === null")
    assert page.locator("#video-gallery .video-clip").count() == 2
    print("PASS a cleared upload permits the next upload", flush=True)
    replaced = page.evaluate(
        """targetId => {
          const studio = document.getElementById('video-studio');
          const file = new File([window.editSelectionBlob], 'replace-me.webm', {type: 'video/webm'});
          studio.addVideoFiles([file]);
          studio.editThisClip(targetId);
          studio.clearEditTarget();
          return studio.addVideoFiles([file]);
        }""",
        target,
    )
    assert replaced
    page.locator("#video-source-list .video-source-remove").click()
    print("PASS an explicit gallery input releases the previous temporary upload", flush=True)
    duplicates = page.evaluate(
        """async () => {
          const studio = document.getElementById('video-studio');
          const settings = {operationId: 'selection-test', modelName: 'LTX-2.5',
            width: 96, height: 64, numFrames: 24, frameRate: 24, duration: 1};
          await studio.addGeneratedClip(window.editSelectionBlob, settings);
          await studio.addGeneratedClip(window.editSelectionBlob, settings);
          const stubSettings = {...settings, operationId: 'selection-stub'};
          const output = {width: 96, height: 64, num_frames: 24, frame_rate: 24};
          studio.addStubClip(output, stubSettings);
          studio.addStubClip(output, stubSettings);
          return studio.clips.filter(clip => clip.metadata?.operationId).map(clip => clip.id);
        }"""
    )
    assert duplicates == ["video-operation-selection-test", "video-operation-selection-stub"]
    print("PASS repeated operation results create one gallery entry", flush=True)
    page.evaluate("targetId => document.getElementById('video-studio').removeClip(targetId)", target)
    assert page.evaluate(
        "targetId => !document.getElementById('video-studio').clips.some(clip => clip.id === targetId)", target
    )
    print("PASS explicit gallery deletion still removes the clip", flush=True)
    metadata = page.evaluate(
        """async () => {
          const studio = document.getElementById('video-studio');
          const settings = {operationId: 'metadata-priority', modelName: 'LTX-2.5',
            width: 96, height: 64, numFrames: 24, frameRate: 24, duration: 1};
          await studio.addGeneratedClip(window.editSelectionBlob, settings);
          const native = {...settings, nativeMetadata: true, references: [{name: 'reference.png'}],
            audioName: 'voice.wav', look: 'Watercolor', effectFile: 'effect.safetensors', stage2: false};
          await studio.addGeneratedClip(window.editSelectionBlob, native);
          const clip = studio.clips.find(clip => clip.metadata?.operationId === settings.operationId);
          await studio.galleryStore.keepVideo({...clip, nativeMetadata: false,
            metadata: {...clip.metadata, look: '', references: [], audio: ''}}, window.editSelectionBlob);
          const records = await studio.galleryStore.loadVideos();
          return {live: clip.metadata, saved: records.find(record => record.id === clip.id).metadata};
        }"""
    )
    for version in metadata.values():
        assert version["look"] == "Watercolor"
        assert version["audio"] == "voice.wav"
        assert version["references"] == [{"name": "reference.png"}]
        assert version["effectFile"] == "effect.safetensors" and version["stage2"] is False
    print("PASS native video metadata upgrades a shared fallback and survives later writes", flush=True)
    browser.close()
