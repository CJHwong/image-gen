"""Bounded gallery loading, legacy Voice migration and wake-lock lifecycle; stub only.

Usage: uv run --with playwright python tests/e2e/verify_gallery_resources.py <port>
"""

import base64
import io
import math
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

URL = f"http://127.0.0.1:{sys.argv[1]}"
COUNT = 256
png = io.BytesIO()
Image.new("RGB", (512, 512), "#527f93").save(png, format="PNG")
audio = io.BytesIO()
with wave.open(audio, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(8000)
    wav.writeframes(b"".join(struct.pack("<h", int(math.sin(i * 0.3) * 500)) for i in range(1600)))
with tempfile.TemporaryDirectory() as scratch:
    video = Path(scratch) / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=128x128:r=8",
            "-t",
            "0.25",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    payload = {
        "png": base64.b64encode(png.getvalue()).decode(),
        "audio": base64.b64encode(audio.getvalue()).decode(),
        "video": base64.b64encode(video.read_bytes()).decode(),
        "count": COUNT,
    }

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL + "/api/v1/openapi.json")
    page.evaluate(
        """async ({png, audio, video, count}) => {
      const blob = (data, type) => new Blob([Uint8Array.from(atob(data), c => c.charCodeAt(0))], {type});
      const image = blob(png, 'image/png'), wav = blob(audio, 'audio/wav'), mp4 = blob(video, 'video/mp4');
      async function seed(name, storeName, records) {
        const db = await new Promise((resolve, reject) => {
          const request = indexedDB.open(name, 1);
          request.onupgradeneeded = () => request.result.createObjectStore(storeName, name === 'studio-voice' ? undefined : {keyPath: 'id'});
          request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
        });
        await new Promise((resolve, reject) => {
          const tx = db.transaction(storeName, 'readwrite'), store = tx.objectStore(storeName);
          records.forEach(record => name === 'studio-voice' ? store.put(record, 'project') : store.put(record));
          tx.oncomplete = resolve; tx.onabort = () => reject(tx.error);
        }); db.close();
      }
      const ids = Array.from({length: count}, (_, i) => i + 1), now = Date.now();
      await seed('studio', 'images', ids.map(id => ({id, number:id, png:image, mode:'generate', prompt:'Resource scene ' + id,
        seed:id, width:512, height:512, backend:'Test', at:now + id})));
      await seed('studio-video-gallery', 'clips', ids.map(id => ({id:'v-' + id, name:'Resource ' + id, mp4,
        duration:0.25, createdAt:now + id, metadata:{prompt:'Resource scene ' + id, width:128, height:128, modelName:'Test'}})));
      await seed('studio-voice', 'state', [{script:'', backend:'drama3', mode:'generate', selectedId:'a-' + count,
        segments:ids.map(id => ({id:'s-' + id, text:'Resource scene ' + id, inScript:false, selected:'a-' + id,
          takes:[{id:'a-' + id, blob:wav, createdAt:now + id, duration:0.2, model:'Test', mode:'generate', peaks:[0.2,0.4,0.3]}]}))}]);
    }""",
        payload,
    )
    context.add_init_script("""window.mediaAudit = {gets:[], all:0, urls:new Map(), wake:0, release:0};
      const get = IDBObjectStore.prototype.get, all = IDBObjectStore.prototype.getAll;
      IDBObjectStore.prototype.get = function(key) { mediaAudit.gets.push([this.name, key]); return get.call(this, key); };
      IDBObjectStore.prototype.getAll = function(...args) { mediaAudit.all++; return all.apply(this,args); };
      const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
      URL.createObjectURL = blob => { const url = create(blob); mediaAudit.urls.set(url,blob.type); return url; };
      URL.revokeObjectURL = url => { mediaAudit.urls.delete(url); return revoke(url); };
      Object.defineProperty(navigator, 'wakeLock', {value:{request: async () => {
        mediaAudit.wake++; const lock = new EventTarget(); lock.released = false;
        lock.release = async () => { if (!lock.released) { lock.released = true; mediaAudit.release++; lock.dispatchEvent(new Event('release')); } };
        return lock;
      }}});
    """)
    page.goto(URL)
    page.wait_for_function(
        "typeof kept !== 'undefined' && kept && gallery.length === 256 && videoStudio.clips.length === 256 && voiceStudio.takesCount === 256"
    )
    page.wait_for_function("gallery.find(item => item.id === view)?.src")
    initial = page.evaluate(
        "({gets:mediaAudit.gets.filter(([store]) => ['images','clips','media'].includes(store)).length, all:mediaAudit.all, originalImages:[...mediaAudit.urls.values()].filter(type => type === 'image/png').length})"
    )
    assert initial["all"] == 0, initial
    assert initial["gets"] < 60, initial
    assert initial["originalImages"] <= 2, initial
    print("PASS initial restore: 768 metadata records, bounded media reads, no media getAll", initial, flush=True)
    page.evaluate("""async () => {
      const {loadVoice,loadVoiceTake} = await import('/page/lib/voice-store.js');
      const state = await loadVoice();
      if (state.segments.some(s => s.takes.some(t => t.blob))) throw Error('Audio still embedded in project');
      if (!(await loadVoiceTake('a-1') instanceof Blob)) throw Error('Legacy audio lost in migration');
    }""")
    print("PASS atomic legacy Voice migration preserves audio and removes embedded blobs", flush=True)
    page.wait_for_function(
        "[...document.querySelectorAll('#strip gallery-media img')].some(img => img.complete && img.naturalWidth && img.getBoundingClientRect().width > 0)"
    )
    for workspace in ("image", "video", "voice"):
        page.locator(f"#media-{workspace}-mode").click()
        gallery_ui = page.locator(f'gallery-browser[workspace="{workspace}"]')
        gallery_ui.locator(".gallery-browse-toggle").click()
        expect(gallery_ui.get_by_role("status")).to_contain_text("256 of 256")
        assert gallery_ui.locator(".gallery-card").count() < 60
        if workspace == "image":
            page.wait_for_function(
                "[...document.querySelectorAll('gallery-browser[workspace=image] gallery-media img')].some(img => img.complete && img.naturalWidth && img.getBoundingClientRect().height > 0)"
            )
        gallery_ui.locator(".gallery-card-pick").first.focus()
        page.keyboard.press("End")
        page.wait_for_function(
            "workspace => document.activeElement?.dataset.itemId === (workspace === 'image' ? '1' : workspace === 'video' ? 'v-1' : 'a-1')",
            arg=workspace,
        )
        page.keyboard.press("Home")
        page.wait_for_function(
            "workspace => document.activeElement?.dataset.itemId === (workspace === 'image' ? '256' : workspace === 'video' ? 'v-256' : 'a-256')",
            arg=workspace,
        )
        grid = gallery_ui.locator(".gallery-browser-grid")
        assert grid.evaluate("el => el.scrollHeight > el.clientHeight * 5")
        grid.evaluate("el => { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event('scroll')); }")
        page.wait_for_function(
            "workspace => [...document.querySelectorAll(`gallery-browser[workspace=${workspace}] .gallery-card-pick`)].some(el => el.dataset.itemId === (workspace === 'image' ? '1' : workspace === 'video' ? 'v-1' : 'a-1'))",
            arg=workspace,
        )
        assert gallery_ui.locator(".gallery-card").count() < 60
        gallery_ui.get_by_role("searchbox").fill("Resource scene 173")
        expect(gallery_ui.locator(".gallery-card")).to_have_count(1)
        gallery_ui.locator(".gallery-card-pick").click()
        if workspace == "image":
            page.wait_for_function("view === 173 && gallery.find(x => x.id === 173)?.src")
        elif workspace == "video":
            page.wait_for_function("videoStudio.selectedClipId === 'v-173' && Boolean(videoStudio.selectedClip()?.url)")
            page.evaluate("videoStudio.removeClip('v-173')")
            page.wait_for_function("Boolean(videoStudio.selectedClip()?.url)")
        else:
            page.wait_for_function(
                "voiceStudio.previewItem?.take?.id === 'a-173' && Boolean(voiceStudio.previewItem?.take?.blob)"
            )
        gallery_ui.get_by_role("searchbox").fill("")
        gallery_ui.locator(".gallery-browse-toggle").click()
        print(f"PASS {workspace}: bounded cards, full-range scrolling, Home/End, search, lazy preview", flush=True)
    page.evaluate("""async () => {
      const {screenAwake} = await import('/page/lib/screen-awake.js');
      const controller = screenAwake();
      controller.set(true); controller.set(true); await new Promise(r => setTimeout(r, 20));
      if (mediaAudit.wake !== 1) throw Error('Duplicate/missing wake request');
      controller.set(false); await new Promise(r => setTimeout(r,20));
      if (mediaAudit.release !== 1) throw Error('Wake lock not released');
      controller.set(true); await new Promise(r => setTimeout(r,20));
      Object.defineProperty(document, 'visibilityState', {value:'hidden', configurable:true});
      document.dispatchEvent(new Event('visibilitychange')); await new Promise(r => setTimeout(r,20));
      if (mediaAudit.release !== 2) throw Error('Hidden page kept its lock');
      Object.defineProperty(document, 'visibilityState', {value:'visible', configurable:true});
      document.dispatchEvent(new Event('visibilitychange')); await new Promise(r => setTimeout(r,20));
      if (mediaAudit.wake !== 3) throw Error('Visible busy page did not reacquire');
      controller.close();
      delete document.visibilityState;
      const request = navigator.wakeLock.request;
      let resolve;
      navigator.wakeLock.request = () => new Promise(r => {resolve=r;});
      const late = screenAwake(); late.set(true); late.set(false);
      let released = false; resolve({release:async () => {released=true;}});
      await new Promise(r => setTimeout(r,20)); late.close();
      if (!released) throw Error('Late lock leaked after operation completed');
      navigator.wakeLock.request = async () => {throw new Error('Denied');};
      const denied = screenAwake(); denied.set(true); await new Promise(r => setTimeout(r,20)); denied.close();
      navigator.wakeLock.request = request;
    }""")
    print(
        "PASS wake lock: deduplication, idle/hidden release, visible reacquisition, late response and denial",
        flush=True,
    )
    page.evaluate("""async () => {
      const entry = gallery.find(item => item.id === view), original = entry.src;
      const metadata = {...entry, nativeMetadata:true}; delete metadata.src; delete metadata.before;
      admit(metadata);
      if (entry.src !== original || !(await fetch(original)).ok) throw Error('Metadata enrichment revoked the preview');
    }""")
    print("PASS metadata-only enrichment preserves the loaded image URL", flush=True)
    second = context.new_page()
    second.add_init_script("""const listen = BroadcastChannel.prototype.addEventListener;
      BroadcastChannel.prototype.addEventListener = function(type, callback, ...rest) {
        return listen.call(this, type, event => {
          if (event.data?.kind === 'prepare-forget') setTimeout(() => callback.call(this,event),800);
          else callback.call(this,event);
        }, ...rest);
      };
    """)
    second.goto(URL)
    second.wait_for_function(
        "typeof kept !== 'undefined' && kept && gallery.length === 256 && videoStudio.clips.length === 255 && voiceStudio.takesCount === 256"
    )
    page.evaluate("""async () => {
      const preparation = kept.prepareForget();
      while (!voiceStudio.forgettingMedia || !voiceStudio.segments.every(s => s.takes.every(t => t.blob && !t.stored)))
        await new Promise(r => setTimeout(r,10));
      voiceStudio.persist(true); await voiceStudio.saved;
      if (!voiceStudio.segments.every(s => s.takes.every(t => t.blob))) throw Error('Media evicted after readiness');
      await preparation;
      keeping=false; kept.announce(false); await videoStudio.setKeeping(false); await voiceStudio.setKeeping(false);
    }""")
    for tab in (page, second):
        tab.wait_for_function("keeping === false")
        assert tab.evaluate(
            "gallery.every(x => x.src) && videoStudio.clips.filter(x => !x.stub).every(x => x.url) && voiceStudio.segments.every(s => s.takes.every(t => t.blob))"
        )
    print("PASS disabling persistence retains unloaded media in both tabs before clearing stores", flush=True)
    page.evaluate("""async () => {
      const studio = voiceStudio, preview = studio.querySelector('audio-preview');
      const ensure = studio.ensureTake, play = preview.play;
      let resolve, played = false;
      studio.ensureTake = () => new Promise(r => {resolve=r;}); preview.play = () => {played=true;};
      const pending = studio.togglePreviewPlayback(); studio.pausePlayback(); studio.hidden = true;
      resolve(); await pending;
      studio.ensureTake = ensure; preview.play = play; studio.hidden = false;
      if (played) throw Error('Cancelled delayed playback started hidden audio');
    }""")
    print("PASS delayed Voice playback respects pause and workspace departure", flush=True)
    assert not errors, errors
    browser.close()
print("PASS gallery resource regression")
