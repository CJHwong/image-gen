"""Check safe, stable media names and their visible download links."""

import re
import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    page = browser.new_page(accept_downloads=True)
    page.goto(URL)
    names = page.evaluate(
        """async () => {
      const {mediaDownloadName} = await import('/page/lib/download-name.js');
      const at = new Date(2026, 9, 21, 12, 34, 56, 789).getTime();
      const defaults = {kind:'image', text:'A red apple on a table.', at, id:'first'};
      return {
        simple: mediaDownloadName({...defaults, extension:'png'}),
        second: mediaDownloadName({...defaults, id:'second', extension:'png'}),
        repeat: mediaDownloadName({...defaults, extension:'png'}),
        unsafe: mediaDownloadName({...defaults, text:'../C:\\u005c\\u005cUsers/secret? <fish> : "red" | apple*', extension:'png'}),
        unicode: mediaDownloadName({...defaults, text:'一隻貓 café', extension:'png'}),
        empty: mediaDownloadName({...defaults, text:'???', extension:'png'}),
        long: mediaDownloadName({...defaults, text:'hello '.repeat(100), extension:'png'}),
        invalidTime: mediaDownloadName({...defaults, at:'not-a-date', extension:'png'}),
        crop: mediaDownloadName({...defaults, kind:'audio', extension:'wav', start:1.25, end:3.5}),
        video: mediaDownloadName({...defaults, kind:'video', extension:'webm'}),
      };
    }"""
    )
    check(
        "the filename starts with its media type and prompt",
        names["simple"].startswith("image-a-red-apple-on-a-table-"),
    )
    check("the timestamp preserves milliseconds", "20261021-123456789" in names["simple"])
    check("repeated downloads retain the same filename", names["simple"] == names["repeat"])
    check("different outputs with equal timestamps have different filenames", names["simple"] != names["second"])
    check("unsafe filename characters cannot form paths", not re.search(r'[<>:"/\\|?*\x00-\x1f]', names["unsafe"]))
    check("Unicode text remains readable", names["unicode"].startswith("image-一隻貓-cafe-"))
    check("punctuation-only prompts use a useful fallback", names["empty"].startswith("image-untitled-"))
    check("long prompts produce bounded filenames", len(names["long"]) <= 120)
    check("missing legacy timestamps produce valid stable names", "NaN" not in names["invalidTime"])
    check(
        "audio crops identify the selected seconds", "-1.25-3.5s-" in names["crop"] and names["crop"].endswith(".wav")
    )
    check(
        "video format retains its real extension",
        names["video"].startswith("video-") and names["video"].endswith(".webm"),
    )
    page.fill("#prompt", "A red apple on a table.")
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    page.wait_for_selector("#strip .frame", timeout=60000)
    page.wait_for_selector("#go[data-state='idle']", timeout=60000)
    link = page.locator("#stage-bar a[download]")
    with page.expect_download() as image_download:
        link.click()
    image_name = image_download.value.suggested_filename
    check("the Image action downloads with its prompt", image_name.startswith("image-a-red-apple-on-a-table-"))
    downloads = []
    page.on("download", lambda download: downloads.append(download.suggested_filename))
    page.click("#download-gallery")
    page.wait_for_timeout(1000)
    check("Image Download all keeps the individual filename", image_name in downloads)
    check(
        "Image metadata has a dated filename",
        any(re.fullmatch(r"image-metadata-\d{8}-\d{9}\.json", name) for name in downloads),
    )

    page.click("#media-video-mode")
    page.wait_for_function("typeof document.getElementById('video-studio').addGeneratedClip === 'function'")
    page.evaluate(
        """async () => {
      const canvas = document.createElement('canvas');
      canvas.width = 96; canvas.height = 64;
      const stream = canvas.captureStream(12);
      const recorder = new MediaRecorder(stream, {mimeType:'video/webm'});
      const chunks = [];
      recorder.ondataavailable = event => chunks.push(event.data);
      const stopped = new Promise(resolve => recorder.onstop = resolve);
      recorder.start();
      canvas.getContext('2d').fillRect(0, 0, 96, 64);
      await new Promise(resolve => setTimeout(resolve, 300));
      recorder.stop();
      await stopped;
      stream.getTracks().forEach(track => track.stop());
      await document.getElementById('video-studio').addGeneratedClip(new Blob(chunks, {type:'video/webm'}), {
        prompt:'A blue kite above the sea.', backend:'ltx25_mlx', modelName:'LTX-2.5',
        width:96, height:64, numFrames:12, frameRate:12, duration:1, seed:7,
      });
    }"""
    )
    with page.expect_download() as video_download:
        page.locator("#video-output-details a[download]").click()
    video_name = video_download.value.suggested_filename
    check(
        "the Video action uses its prompt and original format",
        video_name.startswith("video-a-blue-kite-above-the-sea-") and video_name.endswith(".webm"),
    )
    downloads.clear()
    page.click("#video-gallery-download")
    page.wait_for_timeout(1000)
    check("Video Download all keeps the individual filename", video_name in downloads)
    check(
        "Video metadata has a dated filename",
        any(re.fullmatch(r"video-metadata-\d{8}-\d{9}\.json", name) for name in downloads),
    )
    page.evaluate(
        """async () => {
      await import('/page/components/audio-preview.js');
      const {waveBytes} = await import('/page/lib/voice-audio.js');
      const preview = document.createElement('audio-preview');
      preview.id = 'download-name-audio';
      preview.downloadText = 'The morning sun shines.';
      preview.downloadAt = new Date(2026, 9, 21, 12, 34, 56, 789).getTime();
      preview.downloadId = 'test-voice';
      preview.blob = waveBytes(Float32Array.from({length:24000}, (_, index) => Math.sin(index / 10) / 2), 24000);
      document.body.append(preview);
    }"""
    )
    page.wait_for_function("document.getElementById('download-name-audio').ready")
    with page.expect_download() as audio_download:
        page.evaluate("void document.getElementById('download-name-audio').action('download')")
    audio_name = audio_download.value.suggested_filename
    check(
        "the Audio action uses its script and original format",
        audio_name.startswith("audio-the-morning-sun-shines-") and audio_name.endswith(".wav"),
    )
    page.evaluate(
        "() => { const preview = document.getElementById('download-name-audio'); preview.start = 0.25; preview.end = 0.75; }"
    )
    with page.expect_download() as crop_download:
        page.evaluate("void document.getElementById('download-name-audio').action('download')")
    check(
        "actual cropped audio downloads identify their selected range",
        "-0.25-0.75s-" in crop_download.value.suggested_filename,
    )
    browser.close()
