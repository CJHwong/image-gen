"""Check bounded, local-only gallery motion against a stub; no model or GPU run."""

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory(prefix="gallery-motion-") as temporary:
    video = Path(temporary) / "motion.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1920x1080:rate=24",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(video),
        ],
        check=True,
    )
    encoded = base64.b64encode(video.read_bytes()).decode()

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors, requests = [], []
    media_requests = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.on(
        "request",
        lambda request: (
            media_requests.append(request.url)
            if request.resource_type == "media" and request.url.startswith(("http:", "https:"))
            else None
        ),
    )
    page.goto("http://127.0.0.1:" + sys.argv[1], wait_until="domcontentloaded")
    page.wait_for_function("Boolean(customElements.get('video-gallery-preview'))")
    page.evaluate(
        """encoded => {
      window.captures = []; window.decoderCount = 0; window.peakDecoders = 0;
      const create = document.createElement.bind(document);
      document.createElement = (...args) => {
        const element = create(...args);
        if (args[0] === 'video') {
          captures.push(element);
          element.addEventListener('loadeddata', () => {
            window.peakDecoders = Math.max(window.peakDecoders, captures.filter(video => video.getAttribute('src')).length);
          });
        }
        return element;
      };
      const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
      const grid = create('div'); grid.id = 'motion-check';
      grid.style = 'position:fixed;inset:60px 400px 200px 20px;z-index:999;background:#111;display:grid;grid-template-columns:repeat(4,128px);grid-auto-rows:72px;gap:10px;align-content:start';
      document.body.append(grid);
      for (let index = 0; index < 16; index++) {
        const preview = create('video-gallery-preview'); preview.source = URL.createObjectURL(new Blob([bytes], {type:'video/mp4'}));
        grid.append(preview);
      }
      window.motionStart = performance.now();
    }""",
        encoded,
    )
    page.wait_for_function(
        "[...document.querySelectorAll('#motion-check video-gallery-preview')].every(item => item.sheet)",
        timeout=120000,
    )
    metrics = page.evaluate("""async () => {
      const previews = [...document.querySelectorAll('#motion-check video-gallery-preview')];
      const sizes = await Promise.all(previews.map(async item => (await (await fetch(item.sheet)).blob()).size));
      const bitmap = await createImageBitmap(await (await fetch(previews[0].sheet)).blob());
      const canvas = document.createElement('canvas'); canvas.width = 2048; canvas.height = 72;
      const context = canvas.getContext('2d'); context.drawImage(bitmap,0,0);
      const brightness = Array.from({length:16},(_,i)=>context.getImageData(i*128,0,128,72).data.filter((_,i)=>i%4!==3).reduce((a,b)=>a+b,0)/(128*72*3));
      bitmap.close();

      return {brightness,captureSeconds:(performance.now()-motionStart)/1000, sheetBytes:sizes,
        peakDecoders, released:captures.every(video=>!video.getAttribute('src')),
        loopSeconds:previews.map(item=>item.seconds),
        animations:previews.map(item=>getComputedStyle(item.querySelector('.video-gallery-sheet image')).animationPlayState)};
    }""")
    session = browser.new_browser_cdp_session()
    before = {item["id"]: item["cpuTime"] for item in session.send("SystemInfo.getProcessInfo")["processInfo"]}
    page.wait_for_timeout(3000)
    after = session.send("SystemInfo.getProcessInfo")["processInfo"]
    metrics["loopCpuSecondsOver3s"] = sum(
        max(0, item["cpuTime"] - before[item["id"]]) for item in after if item["id"] in before
    )
    metrics["decodedSheetMiB"] = 16 * 2048 * 72 * 4 / 1024**2
    assert metrics["peakDecoders"] == 1, metrics
    assert metrics["released"] and all(value == 2 for value in metrics["loopSeconds"]), metrics
    assert all(value == "running" for value in metrics["animations"]), metrics
    assert max(metrics["sheetBytes"]) < 100000, metrics
    assert not media_requests, media_requests
    assert min(metrics["brightness"]) > 80, (
        "Every captured color-bar frame must contain video pixels, including frame zero"
    )
    if len(sys.argv) > 2:
        page.screenshot(path=sys.argv[2])
    count = page.evaluate("captures.length")
    for action in ("blocked", "hidden", "offscreen", "reduced"):
        if action == "reduced":
            page.emulate_media(reduced_motion="reduce")
        else:
            page.evaluate(
                """action => {
              if (action==='blocked') document.querySelectorAll('#motion-check video-gallery-preview').forEach(item=>item.blocked=true);
              if (action==='hidden') {Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));}
              if (action==='offscreen') document.querySelector('#motion-check').style.display='none';
            }""",
                action,
            )
        page.wait_for_function(
            "[...document.querySelectorAll('#motion-check video-gallery-preview')].every(item=>!item.sheet)"
        )
        if action == "reduced":
            page.emulate_media(reduced_motion="no-preference")
        else:
            page.evaluate(
                """action => {
              if (action==='blocked') document.querySelectorAll('#motion-check video-gallery-preview').forEach(item=>item.blocked=false);
              if (action==='hidden') {delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));}
              if (action==='offscreen') document.querySelector('#motion-check').style.display='grid';
            }""",
                action,
            )
        page.wait_for_function(
            "[...document.querySelectorAll('#motion-check video-gallery-preview')].every(item=>item.sheet)"
        )
        assert page.evaluate("captures.length") == count, action + " should reuse cached image strips"
    page.evaluate("document.querySelector('#motion-check').remove()")
    assert not errors, errors
    print(
        "PASS sixteen 1080p sources: simultaneous two-second loops; no network; one decoder; visibility, cache and reduced-motion checks"
    )
    print(json.dumps(metrics))
    browser.close()
