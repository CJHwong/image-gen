"""Real-run check of the images the browser keeps, across a reload and between tabs.

It makes two small images. The stub is enough, since this checks the page, not a model:
    uv run studio --stub --port <port>
Then:
    uv run --with playwright python tests/e2e/verify_storage.py <port>
"""

import json
import re
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

PORT = sys.argv[1]
URL = f"http://127.0.0.1:{PORT}/"
results = []


def check(name, passed, detail=""):
    results.append((name, passed))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def frames(page):
    return page.locator("#strip .frame").count()


def run(page, prompt):
    page.fill("#prompt", prompt)
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    page.wait_for_function("!document.body.classList.contains('busy')", timeout=600000)


def leave_blocked(page):
    return page.evaluate("""() => {
        const event = new Event('beforeunload', { cancelable: true });
        window.dispatchEvent(event);
        return event.defaultPrevented;
    }""")


def set_keep(page, on):
    page.click("#theme-toggle")
    item = page.locator("#keep-toggle")
    if (item.get_attribute("aria-checked") == "true") != on:
        item.click()
    else:
        page.keyboard.press("Escape")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    first = context.new_page()
    first.on("dialog", lambda dialog: dialog.accept())
    errors = []
    first.on("pageerror", lambda error: errors.append(str(error)))
    first.goto(URL)
    first.click("#theme-toggle")
    check("keeping is on by default", first.get_attribute("#keep-toggle", "aria-checked") == "true")
    first.keyboard.press("Escape")
    first.click("#advanced summary")
    first.fill("#steps", "2")
    first.dispatch_event("#steps", "input")

    second = context.new_page()
    second.on("dialog", lambda dialog: dialog.accept())
    second.goto(URL)
    run(first, "A red apple on a wooden table.")
    second.wait_for_function("document.querySelectorAll('#strip .frame').length === 1", timeout=10000)
    check("an image made in one tab shows in the other", frames(second) == 1)
    check("the other tab shows its caption", second.inner_text(".prompt-line") == "A red apple on a wooden table.")
    check("no leave warning while the browser keeps the images", not leave_blocked(first))

    run(first, "A green pear on a plate.")
    first.reload()
    first.wait_for_function("document.querySelectorAll('#strip .frame').length === 2", timeout=10000)
    check(
        "a reload brings the images back, newest first", first.inner_text(".prompt-line") == "A green pear on a plate."
    )
    check("the facts come back", "Seed " in first.inner_text(".facts") and "Took " in first.inner_text(".facts"))
    numbers = first.locator("#strip .frame .no").all_inner_texts()
    check("the frame numbers come back", numbers == ["02", "01"], str(numbers))

    saved = []
    first.on("download", lambda download: saved.append(download))
    first.click("#download-gallery")
    deadline = 20
    while len(saved) < 3 and deadline:
        first.wait_for_timeout(500)
        deadline -= 1
    folder = Path(tempfile.mkdtemp(prefix="studio-download-"))
    names = [download.suggested_filename for download in saved]
    for download in saved:
        download.save_as(folder / download.suggested_filename)
    images = [name for name in names if name.endswith(".png")]
    check(
        "Download all saves each image and the prompts",
        len(images) == 2
        and all(re.fullmatch(r"\d{2}-[a-z0-9]+-generate-\d+\.png", name) for name in images)
        and all((folder / name).read_bytes()[:4] == b"\x89PNG" for name in images)
        and names[-1] == "studio-prompts.json",
        str(names),
    )
    facts = json.loads((folder / "studio-prompts.json").read_text()) if "studio-prompts.json" in names else []
    check(
        "the prompts come oldest first, each with its file",
        [fact["prompt"] for fact in facts] == ["A red apple on a wooden table.", "A green pear on a plate."]
        and [fact["file"] for fact in facts] == images,
        str(facts)[:300],
    )

    first.get_by_role("button", name="Edit this", exact=True).click()
    first.wait_for_selector("#refs img", timeout=10000)
    check("a kept image works as a reference", first.locator("#refs img").count() == 1)

    first.get_by_role("button", name="Remove", exact=True).click()
    second.wait_for_function("document.querySelectorAll('#strip .frame').length === 1", timeout=10000)
    check("a removal shows in the other tab", frames(second) == 1)
    first.reload()
    first.wait_for_timeout(1000)
    check("a removal stays after a reload", frames(first) == 1)

    set_keep(first, False)
    second.wait_for_function("document.querySelector('#strip-note').innerText.includes('in this tab')", timeout=10000)
    check("keeping off reaches the other tab", "in this tab" in second.inner_text("#strip-note"))
    check("with keeping off, images warn before a leave", leave_blocked(second))
    third = context.new_page()
    third.goto(URL)
    third.wait_for_timeout(1000)
    check("keeping off empties the browser", frames(third) == 0)
    third.close()

    set_keep(first, True)
    third = context.new_page()
    third.goto(URL)
    third.wait_for_function("document.querySelectorAll('#strip .frame').length === 1", timeout=10000)
    check("keeping on stores what the tab shows", frames(third) == 1)
    first.click("#clear-gallery")
    third.wait_for_function("document.querySelectorAll('#strip .frame').length === 0", timeout=10000)
    check("Clear all clears every tab", frames(third) == 0)
    third.reload()
    third.wait_for_timeout(1000)
    check("Clear all empties the browser", frames(third) == 0)
    check("an empty strip offers no Download all", first.is_hidden("#download-gallery"))
    check("no page errors", not errors, str(errors))
    browser.close()

failed = [name for name, passed in results if not passed]
print(f"\n{len(results) - len(failed)}/{len(results)} passed", "FAILED: " + ", ".join(failed) if failed else "")
sys.exit(1 if failed else 0)
