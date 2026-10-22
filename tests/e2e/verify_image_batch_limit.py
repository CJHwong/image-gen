"""The Image count menu respects the same item limit as the API. Use a fresh qwen21 all-backends stub."""

import io
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

URL = f"http://127.0.0.1:{sys.argv[1]}"
with sync_playwright() as tool:
    browser = tool.chromium.launch()
    for reference_count, count in ((10, 1), (8, 2)):
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.add_init_script("localStorage.setItem('studio-keep','off')")
        page.goto(URL)
        page.wait_for_function("Boolean(formApi && run)")
        page.locator("label[for=mode-edit]").click()
        files = []
        for index in range(reference_count):
            data = io.BytesIO()
            Image.new("RGB", (64, 64), (index * 20, 50, 100)).save(data, format="PNG")
            files.append({"name": f"reference-{index}.png", "mimeType": "image/png", "buffer": data.getvalue()})
        page.locator("#reference").set_input_files(files)
        page.wait_for_function("count => references.length === count", arg=reference_count)
        page.locator("#prompt").fill("make each reference brighter")
        page.locator("#count-toggle").click()
        page.get_by_role("menuitemradio", name="4 images", exact=True).click()
        page.locator("label[for=each-each]").click()
        assert page.locator("#count").input_value() == str(count)
        assert page.evaluate("formApi.imageCount()") == reference_count * count
        page.locator("#count-toggle").click()
        assert page.locator("#count-menu [role=menuitemradio]").count() == count
        page.keyboard.press("Escape")
        page.locator("#advanced summary").click()
        page.locator("#steps").fill("1")
        with page.expect_response("**/image/operations") as submitted:
            page.locator("#go").click()
        response = submitted.value
        assert response.status == 202
        payload = response.request.post_data_json
        assert len(payload["items"]) == reference_count * count <= 16
        assert all(len(item["references"]) == 1 for item in payload["items"])
        page.wait_for_function("!busy() && !sharedOperation", timeout=90000)
        assert page.evaluate("gallery.length") == reference_count * count
        print(
            f"PASS {reference_count} references x {count} results: count menu and prepared batch agree, all outputs imported",
            flush=True,
        )
        page.close()
    browser.close()
