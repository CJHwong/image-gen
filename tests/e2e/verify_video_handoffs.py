"""Check both Image-to-Video handoffs against a fresh stub: <port> <image.png>."""

import sys

from playwright.sync_api import expect, sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:" + sys.argv[1] + "/?workspace=video")

    def edit():
        page.locator("#media-video-mode").click()
        page.locator("label[for=video-mode-edit]").click()
        page.locator("#video-adapters-toggle").click()
        page.locator("#video-adapters").get_by_role("menuitem", name="Custom", exact=False).click()

    edit()
    page.locator("#media-image-mode").click()
    page.locator("#reference").set_input_files(sys.argv[2])
    page.locator("#share-references-video").click()
    expect(page.locator("#video-mode-generate")).to_be_checked()
    expect(page.locator("#video-references .video-reference")).to_have_count(1)
    page.locator("#video-references .video-reference-remove").click()
    edit()
    page.locator("#media-image-mode").click()
    page.locator("#prompt").fill("A blue ceramic cup on a table")
    page.locator("#go").click()
    expect(page.get_by_role("button", name="More actions", exact=True)).to_be_visible(timeout=30000)
    page.get_by_role("button", name="More actions", exact=True).click()
    page.get_by_role("menuitem", name="Use in Video", exact=True).click()
    expect(page.locator("#video-mode-generate")).to_be_checked()
    expect(page.locator("#video-references .video-reference")).to_have_count(1)
    assert not errors, errors
    print("PASS reference and generated-image handoffs switch ordinary Edit to Generate before adding images")
    b.close()
