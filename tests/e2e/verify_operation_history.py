"""Check operation history, display numbers, and native image metadata.

Run against a fresh `uv run studio --stub --all-backends --backend qwen21 --port <port>`.
"""

import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def open_page(context):
    page = context.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(URL)
    page.wait_for_function("typeof kept !== 'undefined' && Boolean(kept)")
    return page


def run(page, prompt, observer=None):
    page.fill("#prompt", prompt)
    page.locator("#steps").evaluate(
        "input => { input.value = input.min; input.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.locator("#go").click()
    if observer:
        observer.locator("#shared-operation:not([hidden])").wait_for()
    page.wait_for_function("!document.body.classList.contains('busy')")


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    first = open_page(context)
    second = open_page(context)
    other_context = browser.new_context(viewport={"width": 1440, "height": 1000})
    other = open_page(other_context)
    first.locator("#look summary").click()
    first.locator("#look-rows .look-row-toggle").first.click()
    first.get_by_role("button", name="Watercolor", exact=True).click()

    def deliver_after_shared_copy(route):
        response = route.fetch()
        first.wait_for_function("gallery.length === 1 && !gallery[0].nativeMetadata")
        route.fulfill(response=response)

    first.route("**/generate", deliver_after_shared_copy)
    run(first, "a copper cup", other)
    first.unroute("**/generate", deliver_after_shared_copy)
    other.locator("#shared-operation").wait_for(state="hidden")
    assert other.locator("#strip .frame").count() == 0
    print("PASS another browser library follows status without importing UI output", flush=True)
    second.wait_for_function("gallery.length === 1")
    for page in (first, second):
        assert page.locator("#strip .frame .no").all_inner_texts() == ["01"]
    second.wait_for_function("Boolean(gallery[0].look?.labels?.includes('Watercolor'))")
    print("PASS shared identities retain ordinary display numbers", flush=True)
    first.evaluate(
        """async () => {
          await kept.keep({...gallery[0], nativeMetadata: false, typed: 'fallback text', look: null});
        }"""
    )
    first.reload()
    first.wait_for_function("gallery.length === 1")
    assert first.evaluate("Boolean(gallery[0].look?.labels?.includes('Watercolor'))")
    assert first.evaluate("gallery[0].typed") == "a copper cup"
    print("PASS a shared fallback cannot overwrite native prompt and Look metadata", flush=True)
    first.get_by_role("button", name="Remove", exact=True).click()
    first.wait_for_function("gallery.length === 0")
    first.reload()
    first.wait_for_timeout(1000)
    assert first.locator("#strip .frame").count() == 0, first.evaluate(
        """() => ({images: gallery.map(entry => ({id:entry.id, operationId:entry.operationId})),
          seen: sessionStorage.getItem('studio-seen-operations')})"""
    )
    fresh = open_page(context)
    fresh.wait_for_timeout(1000)
    assert fresh.locator("#strip .frame").count() == 0
    print("PASS deleted UI results stay deleted after reload and in a new tab", flush=True)

    first.locator("#theme-toggle").click()
    first.locator("#keep-toggle").click()
    first.keyboard.press("Escape")
    run(first, "a temporary pear")
    first.wait_for_function("gallery.length === 1")
    fresh = open_page(context)
    fresh.wait_for_timeout(1000)
    assert fresh.locator("#strip .frame").count() == 0
    first.reload()
    first.wait_for_timeout(1000)
    assert first.locator("#strip .frame").count() == 0
    print("PASS completed UI history does not restore unkept images", flush=True)

    first.fill("#prompt", "a temporary partial batch")
    first.locator("#steps").evaluate(
        "input => { input.value = input.min; input.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    first.locator("#count-toggle").click()
    first.get_by_role("menuitemradio", name="2 images", exact=True).click()
    first.locator("#go").click()
    first.wait_for_function("gallery.length === 1 && document.body.classList.contains('busy')")
    assert context.request.post(URL + "/cancel").status == 204
    first.wait_for_function("!document.body.classList.contains('busy')")
    assert first.evaluate("gallery.length") == 1
    first.reload()
    first.wait_for_timeout(1000)
    assert first.evaluate("gallery.length") == 0
    print("PASS a consumed native cancellation does not restore an unkept partial batch", flush=True)

    response = context.request.post(URL + "/api/v1/images/generate", data={"prompt": "an API pear", "steps": 1})
    assert response.status == 200
    isolated = browser.new_context(viewport={"width": 1440, "height": 1000})
    api_page = open_page(isolated)
    api_page.wait_for_function("gallery.length === 1")
    assert api_page.locator("#strip .frame .no").all_inner_texts() == ["01"]
    assert api_page.evaluate("gallery[0].prompt") == "an API pear"
    print("PASS a fresh browser imports historical API results", flush=True)
    pending = isolated.request.post(
        URL + "/api/v1/operations", data={"kind": "image", "prompt": "a result after Clear all", "steps": 2}
    )
    assert pending.status == 202
    api_page.locator("#shared-operation:not([hidden])").wait_for()
    api_page.locator("#clear-gallery").click()
    api_page.wait_for_function("gallery.length === 1 && gallery[0].prompt === 'a result after Clear all'")
    api_page.evaluate(
        "new BroadcastChannel('studio-gallery').postMessage({kind: 'clear', clearedAt: gallery[0].at - 1})"
    )
    api_page.wait_for_timeout(250)
    assert api_page.evaluate("gallery.length") == 1
    print("PASS Clear all permits new output and a delayed clear preserves it", flush=True)
    api_page.get_by_role("button", name="Remove", exact=True).click()
    api_page.wait_for_function("gallery.length === 0")
    api_page.reload()
    api_page.wait_for_timeout(1000)
    assert api_page.locator("#strip .frame").count() == 0
    fresh = open_page(isolated)
    fresh.wait_for_timeout(1000)
    assert fresh.locator("#strip .frame").count() == 0
    print("PASS deleted API results stay deleted in their browser library", flush=True)
    video = isolated.request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "video",
            "prompt": "a historical API video",
            "width": 384,
            "height": 384,
            "num_frames": 9,
            "frame_rate": 24,
            "seed": 7,
        },
    ).json()
    api_page.wait_for_function(
        "id => document.getElementById('video-studio').clips.some(clip => clip.metadata?.operationId === id)",
        arg=video["id"],
    )
    clip_id = "video-operation-" + video["id"]
    api_page.evaluate(
        "id => { const clip = document.getElementById('video-studio').clips.find(clip => clip.id === id); new BroadcastChannel('studio-gallery').postMessage({kind: 'video-clear', clearedAt: clip.createdAt - 1}); }",
        clip_id,
    )
    api_page.wait_for_timeout(250)
    assert api_page.evaluate(
        "id => document.getElementById('video-studio').clips.some(clip => clip.id === id)", clip_id
    )
    print("PASS a delayed clear preserves a newer video result", flush=True)
    api_page.evaluate("id => document.getElementById('video-studio').removeClip(id)", clip_id)
    api_page.reload()
    api_page.wait_for_timeout(1000)
    fresh = open_page(isolated)
    fresh.wait_for_timeout(1000)
    for page in (api_page, fresh):
        assert not page.evaluate(
            "id => document.getElementById('video-studio').clips.some(clip => clip.id === id)", clip_id
        )
    print("PASS deleted API videos stay deleted after reload and in a new tab", flush=True)
    next_video = isolated.request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "video",
            "prompt": "a second API video",
            "width": 384,
            "height": 384,
            "num_frames": 9,
            "frame_rate": 24,
        },
    ).json()
    api_page.wait_for_function(
        "id => document.getElementById('video-studio').clips.some(clip => clip.metadata?.operationId === id)",
        arg=next_video["id"],
    )
    api_page.evaluate("document.getElementById('video-studio').clearVideoGallery()")
    api_page.reload()
    api_page.wait_for_timeout(1000)
    fresh = open_page(isolated)
    fresh.wait_for_timeout(1000)
    for page in (api_page, fresh):
        assert page.evaluate("document.getElementById('video-studio').clips.length") == 0
    print("PASS Clear all preserves removal of historical API videos", flush=True)
    browser.close()
