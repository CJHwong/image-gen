"""Real-run check of the page against a live studio server on the qwen21 backend.

It generates and edits real images, so it takes minutes. Screenshots go to a
temporary directory, printed at the start.

Usage: uv run --with playwright python tests/e2e/verify_page.py <port>
"""

import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

PORT = sys.argv[1]
OUT = tempfile.mkdtemp(prefix="studio-e2e-") + "/"
print("Screenshots:", OUT)
results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), detail))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def leave_blocked(page):
    return page.evaluate("""() => {
        const event = new Event('beforeunload', { cancelable: true });
        window.dispatchEvent(event);
        return event.defaultPrevented;
    }""")


def wait_idle(page):
    page.wait_for_function("!document.body.classList.contains('busy')", timeout=600000)
    time.sleep(0.5)


def button(page, name):
    return page.get_by_role("button", name=name, exact=True)


def selection(page):
    return page.evaluate(
        "() => { const p = document.getElementById('prompt'); return p.value.slice(p.selectionStart, p.selectionEnd); }"
    )


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
    errors = []
    page.on("console", lambda message: message.type == "error" and errors.append(message.text))
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(f"http://127.0.0.1:{PORT}/")
    page.screenshot(path=OUT + "0-empty.png")

    check("no leave warning when empty", not leave_blocked(page))
    button(page, "Browse templates").click()
    check("empty stage opens templates", page.locator("#templates").is_visible())
    page.keyboard.press("ArrowDown")
    focused = page.evaluate("document.activeElement.textContent")
    check("arrow keys walk the menu", focused.startswith("Product shot"), focused)
    page.keyboard.press("Escape")

    # Templates
    page.click("#templates-toggle")
    check("5 generate templates", page.locator("#templates button").count() == 5)
    page.keyboard.press("Escape")
    check("Escape closes the menu", page.locator("#templates").is_hidden())
    page.click("#templates-toggle")
    page.get_by_role("menuitem", name="Poster with text").click()
    check("first placeholder selected", selection(page) == "[what]", selection(page))
    page.keyboard.type("a night market")
    page.keyboard.press("Tab")
    check("Tab selects the next placeholder", selection(page) == "[lettering style]", selection(page))
    check(
        "run blocked while brackets remain",
        page.is_disabled("#go") and "brackets" in page.inner_text("#go-sub"),
        page.inner_text("#go-sub"),
    )

    # Generate two small images with Cmd+Enter
    page.fill("#prompt", "A ceramic teapot on a linen tablecloth, soft window light from the left.")
    page.dispatch_event("#prompt", "input")
    page.click("#size-chips .chip[data-ratio='4:3']")
    page.click("#tier-sizes button >> nth=0")
    page.click("#advanced summary")
    page.fill("#steps", "8")
    page.dispatch_event("#steps", "input")
    page.click("#count-toggle")
    check("a batch goes up to 4", page.locator("#count-menu [role=menuitemradio]").count() == 4)
    page.get_by_role("menuitemradio", name="2 images").click()
    check(
        "the count menu sets the count",
        page.inner_text("#count-shown") == "×2"  # noqa: RUF001 (the page prints the multiplication sign)
        and page.input_value("#count") == "2",
        page.inner_text("#count-shown"),
    )
    page.click("#look summary")
    page.locator("#look-rows .chip", has_text="Overcast").first.click()
    page.focus("#prompt")
    page.keyboard.press("Meta+Enter")
    page.wait_for_selector(".card .percent:not(:empty)", timeout=300000)
    check("Cmd+Enter starts a run", True)
    bar = page.evaluate("""() => {
        const plate = document.querySelector('.card .plate').getBoundingClientRect();
        const bar = document.querySelector('.card .exposure').getBoundingClientRect();
        return [Math.round(bar.left - plate.left), bar.width / plate.width];
    }""")
    check("the bar grows from the left edge", bar[0] == 0 and bar[1] < 0.5, str(bar))
    card = page.evaluate_handle("document.querySelector('.card')")
    page.click("label[for=mode-edit]")
    check(
        "a mode switch keeps the running frame",
        page.evaluate("(card) => card === document.querySelector('.card')", card),
    )
    page.click("label[for=mode-generate]")
    check(
        "the count is part of the run button",
        page.evaluate(
            "document.getElementById('count-toggle').previousElementSibling === document.getElementById('go')"
        ),
    )
    check("the count is locked while running", page.is_disabled("#count-toggle"))
    check("leave warning while running", leave_blocked(page))
    check("tab title shows progress", page.title().startswith("("), page.title())
    check(
        "run button disabled while running",
        page.is_disabled("#go") and page.inner_text("#go-busy") == "Generating",
        page.inner_text("#go-busy"),
    )
    page.keyboard.press("Meta+Enter")
    time.sleep(1)
    check("Cmd+Enter while running sends nothing", page.locator("#incoming .chain").count() <= 1)
    time.sleep(1)
    page.screenshot(path=OUT + "1-running.png")
    wait_idle(page)
    check("2 images in the strip", page.locator("#strip .frame:not(.pending)").count() == 2)
    go_box = page.locator("#go").bounding_box()
    check(
        "run button in view with images",
        go_box["y"] + go_box["height"] <= 900 and page.evaluate("document.documentElement.scrollHeight") <= 900,
        f"bottom {go_box['y'] + go_box['height']:.0f}",
    )
    check("leave warning with images", leave_blocked(page))
    learned = page.evaluate("learnedCost[STUDIO.backend.id + ' generate'] || 0")
    check("a run teaches the step rate", 0.3 < learned < 20, f"{learned:.2f} s per step at 1 MP")
    check(
        "the caption keeps only the typed prompt",
        page.inner_text(".prompt-line") == "A ceramic teapot on a linen tablecloth, soft window light from the left.",
        page.inner_text(".prompt-line"),
    )
    check(
        "the model got the look, and the facts say so",
        page.locator(".facts span", has_text="Look: Overcast").count() == 1,
    )
    page.locator("#look-rows .chip", has_text="Overcast").first.click()
    page.fill("#prompt", "")
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Reuse prompt").click()
    check(
        "Reuse prompt brings back the look",
        page.locator("#look-rows .chip[aria-pressed=true]").all_inner_texts() == ["Overcast"]
        and page.input_value("#prompt").startswith("A ceramic teapot"),
    )
    page.locator("#look-rows .chip", has_text="Overcast").first.click()
    check("tab title back to normal", page.title() == "Qwen-Image-2.1", page.title())
    time.sleep(1)
    page.screenshot(path=OUT + "2-result.png")

    # Film frame and pencil mark
    check(
        "image sits in a film frame with its number",
        page.locator(".shot .edge").inner_text().endswith(page.locator("#strip .frame.selected .no").inner_text()),
        page.locator(".shot .edge").inner_text(),
    )
    page.locator("#strip .frame:not(.pending) >> nth=1").click()
    check("picking a frame draws the pencil loop", page.locator("#strip .frame.selected .mark.draw").count() == 1)
    page.evaluate("renderStrip()")
    check(
        "a redraw does not draw it again",
        page.locator("#strip .frame.selected .mark.draw").count() == 0
        and page.locator("#strip .frame.selected .mark").count() == 1,
    )
    page.locator("#strip .frame:not(.pending) >> nth=0").click()

    thumb = page.evaluate_handle("document.querySelector('#strip .frame:not(.pending) img')")
    page.locator("#strip .frame:not(.pending) >> nth=1").click()
    page.locator("#strip .frame:not(.pending) >> nth=0").click()
    check("the strip keeps its thumbnails", page.evaluate("(img) => img.isConnected", thumb))
    check("thumbnails use blob URLs", page.evaluate("(img) => img.src.startsWith('blob:')", thumb))

    # Full screen
    page.mouse.click(200, 200)
    page.keyboard.press("f")
    time.sleep(0.5)
    check("F enters full screen", page.evaluate("document.fullscreenElement === document.querySelector('.work')"))
    first = page.evaluate("view")
    page.keyboard.press("ArrowRight")
    check("ArrowRight shows the next frame", page.evaluate("view") != first)
    page.keyboard.press("ArrowLeft")
    check("ArrowLeft goes back", page.evaluate("view") == first)
    page.screenshot(path=OUT + "2b-fullscreen.png")
    button(page, "Exit full screen (F)").click()
    time.sleep(0.5)
    check("the button leaves full screen", page.evaluate("document.fullscreenElement === null"))

    page.get_by_role("button", name="More actions").click()
    check("More menu opens", page.locator("#more-menu").is_visible())
    page.mouse.click(200, 200)
    check("outside click closes More", page.locator("#more-menu").is_hidden())

    # Edit this
    button(page, "Edit this").click()
    check("Edit this switches to edit", page.is_checked("#mode-edit"))
    check("Edit this leaves one reference", page.locator("#thumbs .thumb").count() == 1)
    check("Edit this clears the prompt", page.input_value("#prompt") == "")
    seed = page.locator(".facts span", has_text="Seed").first.inner_text().split()[-1]
    check("Edit this keeps the seed", page.input_value("#seed") == seed, seed)
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Use as reference").click()
    check("Use as reference adds a second", page.locator("#thumbs .thumb").count() == 2)
    button(page, "Edit this").click()
    check("Edit this resets to one", page.locator("#thumbs .thumb").count() == 1)

    # One-image edit and the compare slider
    page.fill("#prompt", "Change only the teapot's color to glossy cobalt blue. Keep everything else unchanged.")
    page.dispatch_event("#prompt", "input")
    page.click("#edit-sizes button[data-value='512']")
    page.click("#count-toggle")
    page.get_by_role("menuitemradio", name="1 image").click()
    page.click("#go")
    wait_idle(page)
    check(
        "compare slider on the edit",
        page.locator(".compare-range").count() == 1 and page.locator("img.before").count() == 1,
    )
    time.sleep(0.3)
    early = page.evaluate("getComputedStyle(document.querySelector('.pic')).getPropertyValue('--split').trim()")
    time.sleep(1.8)
    late = page.evaluate("getComputedStyle(document.querySelector('.pic')).getPropertyValue('--split').trim()")
    check("the divider sweeps in once", early == "0%" and late == "50%", f"{early} then {late}")
    page.screenshot(path=OUT + "3-compare.png")
    pic = page.locator(".pic").bounding_box()
    tag = page.locator(".compare-tag.left").bounding_box()
    check(
        "tags sit on the image",
        pic["x"] <= tag["x"] <= pic["x"] + 20 and pic["y"] <= tag["y"] <= pic["y"] + 20,
        f"pic {pic['x']:.0f},{pic['y']:.0f} tag {tag['x']:.0f},{tag['y']:.0f}",
    )
    box = page.locator(".compare-range").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.2, box["y"] + box["height"] / 2)
    split = page.evaluate("getComputedStyle(document.querySelector('.pic')).getPropertyValue('--split').trim()")
    check("a click moves the split", split in ("19%", "20%", "21%"), split)
    page.locator("#strip .frame:not(.pending) >> nth=1").click()
    check("no slider on a generate image", page.locator(".compare-range").count() == 0)
    page.locator("#strip .frame:not(.pending) >> nth=0").click()
    check(
        "second view opens at the middle",
        page.evaluate("getComputedStyle(document.querySelector('.pic')).getPropertyValue('--split').trim()") == "50%",
    )

    # Two-image edit: no slider
    page.locator("#strip .frame:not(.pending) >> nth=1").click()
    button(page, "Edit this").click()
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Use as reference").click()
    page.fill("#prompt", "Put the two teapots side by side on one table.")
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    wait_idle(page)
    check(
        "no slider on a two-image edit",
        page.locator("#thumbs .thumb").count() == 2 and page.locator(".compare-range").count() == 0,
    )

    # Mode switch and cancel
    check("edit shows no Look, since qwen21 declares none for it", not page.is_visible("#look"))
    page.click("label[for=mode-generate]")
    page.locator("#look-rows .chip", has_text="Overcast").first.click()
    page.click("label[for=mode-edit]")
    page.click("label[for=mode-generate]")
    check(
        "mode switch clears the look",
        page.locator("#look-rows .chip[aria-pressed=true]").count() == 0
        and page.text_content("#look-values") == "none",
    )
    check("mode switch clears the prompt", page.input_value("#prompt") == "")
    page.fill("#prompt", "A lighthouse on a cliff at dusk.")
    page.dispatch_event("#prompt", "input")
    page.fill("#steps", "20")
    page.dispatch_event("#steps", "input")
    page.click("#go")
    page.wait_for_selector(".card .percent:not(:empty)", timeout=300000)
    page.click(".card .btn")
    wait_idle(page)
    check("cancel ends the run, no new image", page.locator("#strip .frame:not(.pending)").count() == 4)

    # Remove, themes, phone
    page.locator("#strip .frame >> nth=0").click()
    page.get_by_role("button", name="Remove from this tab").click()
    check("remove takes one", page.locator("#strip .frame").count() == 3)
    page.emulate_media(color_scheme="light")
    time.sleep(0.5)
    page.screenshot(path=OUT + "4-light.png")
    page.emulate_media(color_scheme="dark")
    page.set_viewport_size({"width": 390, "height": 844})
    time.sleep(0.5)
    width = page.evaluate("document.documentElement.scrollWidth")
    check("phone has no sideways scroll", width <= 390, str(width))
    page.screenshot(path=OUT + "5-phone.png")
    page.evaluate("window.scrollTo(0, 560)")
    page.screenshot(path=OUT + "6-phone-form.png")
    page.set_viewport_size({"width": 1440, "height": 900})

    page.click("#clear-gallery")
    check("clear empties the strip", page.locator("#strip .frame").count() == 0)
    page.click("label[for=mode-edit]")
    check("edit empty offers a picker", button(page, "Choose an image").is_visible())
    check("no leave warning after clear", not leave_blocked(page))

    # Reduced motion: nothing animates
    page.emulate_media(reduced_motion="reduce")
    animated = page.evaluate("""() => {
        const probe = document.createElement('div');
        probe.innerHTML = '<div class="frame arrive"></div><div class="card waiting"><div class="exposure"></div></div>'
          + MARK.replace('class="mark"', 'class="mark draw"');
        document.getElementById('canvas').append(probe);
        const names = [...probe.querySelectorAll('.frame, .exposure, .mark path')]
          .map(e => getComputedStyle(e).animationName);
        probe.remove();
        return names;
    }""")
    check("reduced motion stops every animation", all(name == "none" for name in animated), str(animated))
    page.emulate_media(reduced_motion="no-preference")
    normal = page.evaluate("""() => {
        const probe = document.createElement('div');
        probe.innerHTML = '<div class="frame arrive"></div>';
        document.getElementById('canvas').append(probe);
        const name = getComputedStyle(probe.firstChild).animationName;
        probe.remove();
        return name;
    }""")
    check("normal motion animates", normal == "join", normal)

    check("no console errors", not errors, "; ".join(errors))
    browser.close()

failed = [name for name, passed, _ in results if not passed]
print(f"\n{len(results) - len(failed)}/{len(results)} passed", "FAILED: " + ", ".join(failed) if failed else "")
