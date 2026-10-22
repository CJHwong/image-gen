"""Video Rewrite stays available independently of the Image rewriter; fresh all-backends stub."""

import io
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    assert page.request.post(URL + "/api/v1/images/backend", data={"backend": "flux2"}).status == 204
    page.goto(URL + "/?workspace=video")
    page.locator("#video-prompt").fill("A paper boat floats.")
    assert page.locator("#video-rewrite-toggle").is_visible()
    with page.expect_request(lambda request: request.url.endswith("/rewrite") and request.method == "POST") as request:
        page.locator("#video-rewrite-toggle").click()
    assert "workspace=video" in request.value.post_data
    page.wait_for_function('!document.body.classList.contains("rewriting")')
    assert "longer version" in page.locator("#video-prompt").input_value()
    print("PASS Video Rewrite works while the Image backend has no rewriter", flush=True)
    output = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(output, format="PNG")
    page.locator("#video-media-upload").set_input_files(
        {"name": "frame.png", "mimeType": "image/png", "buffer": output.getvalue()}
    )
    page.wait_for_function("videoStudio.imageReferences.length === 1")
    page.locator("#video-prompt").fill("The boat turns slowly.")
    with page.expect_request(lambda request: request.url.endswith("/rewrite") and request.method == "POST") as request:
        page.locator("#video-rewrite-toggle").click()
    import json
    from urllib.parse import parse_qs

    body = parse_qs(request.value.post_data)
    assert len(json.loads(body["references"][0])) == 1
    page.wait_for_function('document.querySelector("#video-rewrite-toggle .rewrite-cancel").hidden === false')
    page.locator("#video-rewrite-toggle").click()
    page.wait_for_function('!document.body.classList.contains("rewriting")')
    assert page.locator("#video-prompt").input_value() == "The boat turns slowly."
    print("PASS keyframes select image-to-video rewriting and cancellation keeps the prompt", flush=True)
    assert not errors, errors
    browser.close()
