"""Drive explicit API batches and check shared UI results across all workspaces.

Run against a fresh `uv run studio --stub --all-backends --port <port>`.
"""

import sys
import time

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]
VOICE = "A woman in her thirties, calm, warm and clear, reading a documentary with a neutral American accent and a steady pace."


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


def completed(request, operation_id):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        operation = request.get(URL + "/api/v1/operations/" + operation_id).json()
        if operation["status"] not in ("running", "stopping"):
            return operation
        time.sleep(0.1)
    raise AssertionError("The batch did not finish")


def submit(request, body):
    response = request.post(URL + "/api/v1/operations", data=body)
    check("the batch is accepted", response.status == 202)
    return response.json()


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    pages = [context.new_page(), context.new_page()]
    errors = []
    for page in pages:
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(URL)
    request = context.request
    images = submit(
        request,
        {
            "kind": "image",
            "backend": "qwen21",
            "steps": 1,
            "size": "512x512",
            "items": [{"prompt": "a red pear", "seed": 7}, {"prompt": "a blue cup", "seed": 8}],
        },
    )
    state = completed(request, images["id"])
    check("the image batch succeeds", state["status"] == "succeeded")
    manifest = request.get(URL + state["result_url"]).json()
    check("the image batch retains both ordered items", [item["index"] for item in manifest["items"]] == [1, 2])
    seeds = [request.get(URL + item["result_url"]).json()["images"][0]["seed"] for item in manifest["items"]]
    check("item settings override shared defaults", seeds == [7, 8])
    for page in pages:
        page.wait_for_function("document.querySelectorAll('#strip .frame').length === 2")
    check("both tabs import all image items once", True)

    videos = submit(
        request,
        {
            "kind": "video",
            "backend": "ltx25_mlx",
            "width": 384,
            "height": 384,
            "num_frames": 9,
            "frame_rate": 24,
            "enhance": False,
            "items": [{"prompt": "a red kite", "seed": 7}, {"prompt": "a blue sailboat", "seed": 8}],
        },
    )
    state = completed(request, videos["id"])
    check("the video batch succeeds", state["status"] == "succeeded")
    manifest = request.get(URL + state["result_url"]).json()
    check(
        "the video batch exposes individual result routes",
        len(manifest["items"]) == 2
        and all(request.get(URL + item["result_url"]).status == 200 for item in manifest["items"]),
    )
    for page in pages:
        page.wait_for_function("document.getElementById('video-studio').clips.length === 2")
    check("both tabs import distinct video outputs", True)

    voices = submit(
        request,
        {
            "kind": "voice",
            "backend": "auk_base",
            "mode": "design",
            "voice": VOICE,
            "seconds": 1,
            "items": [{"text": "The first sentence.", "seed": 7}, {"text": "The second sentence.", "seed": 8}],
        },
    )
    state = completed(request, voices["id"])
    check("the voice batch succeeds", state["status"] == "succeeded")
    manifest = request.get(URL + state["result_url"]).json()
    check(
        "voice item results are WAV files",
        all(
            request.get(URL + item["result_url"]).headers["content-type"].startswith("audio/wav")
            for item in manifest["items"]
        ),
    )
    for page in pages:
        page.wait_for_function("document.getElementById('voice-studio').takesCount === 2")
    check("both tabs import voice batch takes", True)

    failure = submit(
        request,
        {
            "kind": "image",
            "backend": "qwen21",
            "steps": 1,
            "size": "512x512",
            "items": [{"prompt": "a yellow lemon", "seed": 9}, {"prompt": ""}],
        },
    )
    state = completed(request, failure["id"])
    check("a failed item terminates its batch", state["status"] == "failed")
    manifest = request.get(URL + state["result_url"]).json()
    check("an invalid batch fails before engine work", len(manifest["items"]) == 0)
    for page in pages:
        page.wait_for_function("document.querySelectorAll('#strip .frame').length === 2")
    check("an invalid batch adds no partial images", True)
    check("there are no browser errors", not errors)
    browser.close()
