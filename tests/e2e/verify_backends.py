"""Real-run check of two backends behind one page: flux2 first, then a switch to qwen21.

studio.toml offers one model, and the page draws no picker for one, so both flags
are needed here. `--backend flux2` opens on flux2, which the opening checks read.
`--all-backends` puts the rest in the picker, which is the only way the switch to
qwen21 has a row to click: `--backend flux2` alone would offer flux2 and the
configured default (Turbo), and the check would have nothing to switch to.

    uv run studio --port <port> --backend flux2 --all-backends
    uv run --with playwright python tests/e2e/verify_backends.py <port>

It makes three small images and loads both models, so it takes a few minutes.
"""

import sys
import time

from playwright.sync_api import sync_playwright

PORT = sys.argv[1]
results = []


def check(name, passed, detail=""):
    results.append(bool(passed))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def wait_idle(page):
    page.wait_for_function("!document.body.classList.contains('busy')", timeout=600000)
    time.sleep(0.5)


def small_run(page, prompt):
    # `#size` is a hidden select the chips drive, so it is set the way the page's own
    # setSelect sets it: the value, then the event that mirrors it into the form.
    page.locator("#size").evaluate(
        "element => { element.value = '512x512'; element.dispatchEvent(new Event('change', {bubbles: true})); }"
    )
    if page.get_attribute("#advanced", "open") is None:
        page.click("#advanced summary")
    page.fill("#steps", "4")
    page.dispatch_event("#steps", "input")
    page.fill("#prompt", prompt)
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    wait_idle(page)


def frames(page):
    return page.locator("#strip .frame:not(.pending)").count()


with sync_playwright() as playwright:
    page = playwright.chromium.launch().new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("console", lambda message: message.type == "error" and errors.append(message.text))
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(f"http://127.0.0.1:{PORT}/")

    check("the page opens on flux2", page.inner_text("h1") == "FLUX.2 klein 9B", page.inner_text("h1"))
    page.click("#backend-toggle")
    # The accessible name of a row is the model's name alone, pinned by the page. That
    # is what is compared, so the description on the row's second line does not join in.
    offered = page.get_by_role("menuitemradio").evaluate_all(
        "nodes => nodes.map((node) => node.getAttribute('aria-label'))"
    )
    check(
        "the picker offers every model the page may use",
        offered == page.evaluate("() => STUDIO.backends.map((backend) => backend[1])") and "Qwen-Image-2.1" in offered,
        str(offered),
    )
    page.keyboard.press("Escape")
    chips = page.locator("#look-rows .chip").all_text_contents()
    check(
        "Look offers only the options flux2 passed",
        page.is_visible("#look") and len(chips) == 11 and "Documentary" not in chips and "3D render" in chips,
        str(chips),
    )
    check("templates show", page.is_visible("#templates-toggle") and page.locator(".empty button").count() > 0)
    if page.get_attribute("#advanced", "open") is None:
        page.click("#advanced summary")
    check("no negative prompt", not page.is_visible("#negative"))
    check("steps default to 25", page.input_value("#steps") == "25", page.input_value("#steps"))
    check("guidance defaults to 4", page.input_value("#guidance") == "4", page.input_value("#guidance"))

    small_run(page, "A red apple on a wooden table, soft window light.")
    check("flux2 makes an image", frames(page) == 1 and "FLUX.2 KLEIN 9B" in page.inner_text(".stage"))
    check(
        "the facts say 512 and 4 steps",
        "512 × 512" in page.inner_text(".facts")  # noqa: RUF001 (the page prints the multiplication sign)
        and "4 steps" in page.inner_text(".facts"),
        page.inner_text(".facts"),
    )
    check(
        "the run learned a flux2 rate",
        # The key is the page's own, and it names the mode, the reference count and
        # whether the run took two passes. Asking costKey() for it keeps this check
        # from going stale when that key gains a field.
        page.evaluate("learnedCost[costKey()] || 0") > 0.5,
        str(page.evaluate("learnedCost")),
    )

    page.get_by_role("button", name="Edit this", exact=True).click()
    check(
        "edit takes up to 4 images",
        "up to 4" in page.inner_text("#refs") or "of 4" in page.inner_text("#refs"),
        page.inner_text("#refs"),
    )
    check("edit uses a size, not a resolution", page.is_visible("#size-chips") and not page.is_visible("#edit-sizes"))
    summary = page.text_content("#advanced-values") or ""
    check("the edit summary names guidance, not CFG", "guidance 4" in summary and "CFG" not in summary, summary)
    small_run(page, "Put a small yellow hat on the apple.")
    check("flux2 edits the image", frames(page) == 2)
    held = frames(page)

    page.click("#backend-toggle")
    # Exact: "Qwen-Image-2.1" is a prefix of Turbo's name, and a substring match would
    # land on Turbo's row and then wait for a switch that never comes.
    with page.expect_navigation(wait_until="domcontentloaded"):
        page.get_by_role("menuitemradio", name="Qwen-Image-2.1", exact=True).click()
    page.wait_for_function("STUDIO.backend.id === 'qwen21'", timeout=600000)
    page.wait_for_function(
        "count => document.querySelectorAll('#strip .frame:not(.pending)').length === count", arg=held
    )
    check("the switch reloads on qwen21", page.inner_text("h1") == "Qwen-Image-2.1")
    check("qwen21 brings back Look and templates", page.is_visible("#look") and page.is_visible("#templates-toggle"))
    # Keeping is on by default, so the reload the switch makes leaves the strip as it
    # was. verify_ui.py checks that on its own, with the theme switch either way.
    check("the switch keeps the strip", frames(page) == held, f"{frames(page)} of {held}")
    small_run(page, "A red apple on a wooden table, soft window light.")
    check(
        "qwen21 adds an image after the switch, and it names qwen21",
        frames(page) == held + 1 and "QWEN IMAGE 2.1" in page.inner_text(".stage"),
        f"{frames(page)} images",
    )
    check("no console errors", not errors, "; ".join(errors))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
