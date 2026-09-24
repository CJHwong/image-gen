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


def toggle_look(page, row, label):
    """Open the Look row, then pick or unpick the option. A pick closes the row again."""
    page.locator("#look-rows .look-row-toggle", has_text=row).click()
    page.locator("#look-rows .chip", has_text=label).first.click()


def selection(page):
    return page.evaluate(
        "() => { const p = document.getElementById('prompt'); return p.value.slice(p.selectionStart, p.selectionEnd); }"
    )


# Each pair is a text colour and the background it sits on, read from the
# theme's custom properties. Custom properties hold the raw hex text.
CONTRAST = """() => {
    const hex = value => {
        const digits = value.trim().replace('#', '');
        if (!/^[0-9a-f]{6}$/i.test(digits)) throw new Error('not a hex colour: ' + value);
        return [0, 2, 4].map(start => parseInt(digits.slice(start, start + 2), 16) / 255);
    };
    const luminance = rgb => {
        const [r, g, b] = rgb.map(c => c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const ratio = (element, text, back) => {
        const style = getComputedStyle(element);
        const [a, b] = [text, back].map(name => luminance(hex(style.getPropertyValue(name))));
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    };
    const root = document.documentElement, stage = document.querySelector('.stage');
    const pairs = {
        'text on chrome': [root, '--text', '--chrome'],
        'text-2 on chrome': [root, '--text-2', '--chrome'],
        'text-3 on chrome': [root, '--text-3', '--chrome'],
        'text-3 on chrome-2': [root, '--text-3', '--chrome-2'],
        'text on hover': [root, '--text', '--chrome-3'],
        'text-2 on hover': [root, '--text-2', '--chrome-3'],
        'run button label': [root, '--on-accent', '--accent-fill'],
        'stage text': [stage, '--text', '--box'],
        'stage text-2': [stage, '--text-2', '--box'],
        'stage text-3': [stage, '--text-3', '--box'],
        'stage text on hover': [stage, '--text', '--chrome-3'],
    };
    return Object.fromEntries(Object.entries(pairs).map(([name, args]) => [name, ratio(...args)]));
}"""


# A probe plate at 40%, measured: where the exposed part sits and how opaque it is.
EXPOSURE = """() => {
    const probe = document.createElement('div');
    probe.className = 'card';
    probe.style.setProperty('--exposed', '40%');
    probe.innerHTML = '<div class="plate"><div class="exposure"></div></div>';
    document.getElementById('canvas').append(probe);
    const plate = probe.querySelector('.plate').getBoundingClientRect();
    const exposure = probe.querySelector('.exposure');
    const box = exposure.getBoundingClientRect();
    const near = (value, target) => Math.abs(value - target) < 0.03;
    const [x, y] = [(box.left - plate.left) / plate.width, (box.top - plate.top) / plate.height];
    const [w, h] = [box.width / plate.width, box.height / plate.height];
    const opacity = Number(getComputedStyle(exposure).opacity);
    probe.remove();
    let kind = 'other';
    if (near(x, 0) && near(w, 0.4) && near(h, 1)) kind = 'sweep';
    if (near(w, 1) && near(h, 0.4) && near(y, 0)) kind = 'drop';
    if (near(w, 1) && near(h, 0.4) && near(y, 0.6)) kind = 'rise';
    if (near(w, 1) && near(h, 1) && near(opacity, 0.4)) kind = 'develop';
    return { kind, x, y, w, h, opacity };
}"""


def check_contrast(page, theme):
    ratios = page.evaluate(CONTRAST)
    low = {name: round(value, 2) for name, value in ratios.items() if value < 4.5}
    check(f"{theme}: every text colour reaches 4.5:1", not low, str(low))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    # A context, not a bare page, so a second tab can share its storage.
    page = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark").new_page()
    errors = []
    page.on("console", lambda message: message.type == "error" and errors.append(message.text))
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(f"http://127.0.0.1:{PORT}/")
    page.screenshot(path=OUT + "0-empty.png")

    check("no leave warning when empty", not leave_blocked(page))
    check("the top plate has no privacy line", page.locator(".topbar .privacy").count() == 0)
    check("the dial shows the weights", page.inner_text(".topbar .badge") == "bf16")
    check("the top plate has no frame counter", page.locator("#counter").count() == 0)
    check("the status is announced", page.get_attribute("#status", "aria-live") == "polite")
    check("the run button announces nothing", page.get_attribute("#go-sub", "aria-live") is None)
    page.evaluate("document.querySelector('#backend-toggle .name').textContent = 'A very long model name '.repeat(8)")
    name = page.evaluate("""() => {
        const name = document.querySelector('#backend-toggle .name');
        return [name.scrollWidth > name.clientWidth, document.querySelector('.topbar').offsetHeight];
    }""")
    check("a long model name truncates in the top plate", name == [True, 52], str(name))
    page.reload()
    check("the status reads ready", page.inner_text("#status") == "Ready", page.inner_text("#status"))
    button(page, "Browse templates").click()
    check("empty stage opens templates", page.locator("#templates").is_visible())
    page.keyboard.press("ArrowDown")
    focused = page.evaluate("document.activeElement.textContent")
    check("arrow keys walk the menu", focused.startswith("Product shot"), focused)
    page.keyboard.press("Escape")

    # Templates
    page.click("#templates-toggle")
    check("7 generate templates", page.locator("#templates button").count() == 7)
    page.set_viewport_size({"width": 1440, "height": 500})
    menu = page.locator("#templates").bounding_box()
    check("the menu fits in a short window", menu["y"] + menu["height"] <= 500, menu)
    last = page.locator("#templates button").last
    last.scroll_into_view_if_needed()
    check("the last template scrolls into view", last.bounding_box()["y"] + last.bounding_box()["height"] <= 500)
    page.set_viewport_size({"width": 1440, "height": 900})
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
    toggle_look(page, "Light", "Overcast")
    page.focus("#prompt")
    page.keyboard.press("Meta+Enter")
    page.wait_for_selector(".card .percent:not(:empty)", timeout=300000)
    check("Cmd+Enter starts a run", True)
    # The percent shows at 0% while the backend still loads, before step 1.
    page.wait_for_function("document.getElementById('status').innerText.startsWith('Step ')", timeout=300000)
    status = page.inner_text("#status")
    check("the status reads the step", status.startswith("Step ") and " of " in status, status)
    bar = page.evaluate("""() => {
        const plate = document.querySelector('.card .plate').getBoundingClientRect();
        const bar = document.querySelector('.card .exposure').getBoundingClientRect();
        return [Math.round(plate.bottom - bar.bottom), bar.height / plate.height];
    }""")
    check("the Kodak print rises from the bottom edge", bar[0] == 0 and bar[1] < 0.5, str(bar))
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
        "the run button turns into Cancel",
        page.is_enabled("#go") and page.inner_text("#go .main") == "Cancel",
        page.inner_text("#go .main"),
    )
    check("the run button shows no step text", page.inner_text("#go-sub") == "", page.inner_text("#go-sub"))
    check("the run button has no fill bar", page.locator("#go .fill").count() == 0)
    check(
        "the card keeps only the plate and the percentage",
        page.locator(".card [data-slot], .card .btn").count() == 0 and page.locator(".card .percent").count() == 1,
    )
    page.keyboard.press("Meta+Enter")
    time.sleep(1)
    check("Cmd+Enter while running sends nothing", page.locator("#incoming .chain").count() <= 1)
    page.focus("#seed")
    page.keyboard.press("Enter")  # an implicit submit clicks the run button, which is Cancel's guard
    time.sleep(1)
    check("Enter in a field while running sends nothing", page.locator("#incoming .chain").count() <= 1)
    check("Enter in a field does not cancel either", "stopping" not in page.get_attribute("body", "class"))
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
    check("no leave warning while the browser keeps the images", not leave_blocked(page))
    check("a plain run says Generated", page.inner_text(".facts .made") == "Generated", page.inner_text(".facts .made"))
    learned = page.evaluate("learnedCost[STUDIO.backend.id + ' generate'] || 0")
    check("a run teaches the step rate", 0.3 < learned < 20, f"{learned:.2f} s per step at 1 MP")
    check(
        "the caption shows the typed prompt, then the Look muted",
        page.inner_text(".prompt-line").startswith(
            "A ceramic teapot on a linen tablecloth, soft window light from the left. Overcast"
        )
        and page.inner_text(".prompt-line .look-said").startswith("Overcast"),
        page.inner_text(".prompt-line"),
    )
    check("the facts do not repeat the Look", page.locator(".facts span", has_text="Look").count() == 0)
    check(
        "the facts name the time",
        page.locator(".facts span", has_text="Took ").count() == 1,
        page.inner_text(".facts"),
    )
    toggle_look(page, "Light", "Overcast")
    page.fill("#prompt", "")
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Reuse prompt").click()
    check(
        "Reuse prompt brings back the look",
        page.locator("#look-rows .chip[aria-pressed=true]").all_text_contents() == ["Overcast"]
        and page.input_value("#prompt").startswith("A ceramic teapot"),
    )
    toggle_look(page, "Light", "Overcast")
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

    page.mouse.click(200, 200)
    first = page.evaluate("view")
    page.keyboard.press("ArrowRight")
    check("ArrowRight steps outside full screen", page.evaluate("view") != first)
    page.keyboard.press("ArrowLeft")
    check("ArrowLeft steps back outside full screen", page.evaluate("view") == first)

    # Full screen
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
    source = page.inner_text(".shot .edge span:last-child")
    button(page, "Edit this").click()
    check("Edit this resets to one", page.locator("#thumbs .thumb").count() == 1)

    # One-image edit and the compare slider
    page.fill("#prompt", "Change only the teapot's color to glossy cobalt blue. Keep everything else unchanged.")
    page.dispatch_event("#prompt", "input")
    page.click("#edit-sizes button[data-value='512']")
    page.click("#count-toggle")
    page.get_by_role("menuitemradio", name="1 image").click()
    # Record every split value from the run on, so the check sees the whole
    # sweep instead of racing it with a fixed-time sample.
    page.evaluate(
        "window.splits = []; (function sample() {"
        " const pic = document.querySelector('.pic');"
        " const split = pic && pic.style.getPropertyValue('--split');"
        " if (split && split !== window.splits[window.splits.length - 1]) window.splits.push(split);"
        " requestAnimationFrame(sample); })()"
    )
    page.click("#go")
    wait_idle(page)
    made = page.inner_text(".facts .made")
    check("an edit names its source frame", made == f"Edited from {source}", made)
    page.get_by_role("button", name=f"Show frame {source}").click()
    check("the source link shows that frame", page.inner_text(".shot .edge span:last-child") == source)
    page.locator("#strip .frame:not(.pending) >> nth=0").click()
    check(
        "compare slider on the edit",
        page.locator(".compare-range").count() == 1 and page.locator("img.before").count() == 1,
    )
    time.sleep(2)
    splits = [float(value.rstrip("%")) for value in page.evaluate("window.splits")]
    check(
        "the divider sweeps in once",
        splits[:1] == [0] and splits[-1:] == [50] and splits == sorted(splits),
        str(splits),
    )
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
    page.click(".facts .compare")
    check(
        "Compare off shows the result alone",
        page.locator(".compare-range").count() == 0
        and page.get_attribute(".facts .compare", "aria-pressed") == "false"
        and page.evaluate("document.activeElement.className") == "compare",
    )
    page.click(".facts .compare")
    check("Compare on brings the slider back", page.locator(".compare-range").count() == 1)
    page.locator("#strip .frame:not(.pending) >> nth=1").click()
    check("no slider on a generate image", page.locator(".compare-range").count() == 0)
    check("no Compare switch on a generate image", page.locator(".facts .compare").count() == 0)
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
    toggle_look(page, "Light", "Overcast")
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
    page.click("#go")  # a double click on Generate must not cancel the run it just started
    time.sleep(0.3)
    check("a click in the first half second does not cancel", "stopping" not in page.get_attribute("body", "class"))
    page.wait_for_selector(".card .percent:not(:empty)", timeout=300000)
    page.click("#go")
    check(
        "Cancel reads Stopping while it stops",
        page.inner_text("#go .main") == "Stopping\u2026",
        page.inner_text("#go .main"),
    )
    wait_idle(page)
    check("cancel ends the run, no new image", page.locator("#strip .frame:not(.pending)").count() == 4)

    # Remove, themes, phone
    page.locator("#strip .frame >> nth=0").click()
    page.get_by_role("button", name="Remove", exact=True).click()
    check("remove takes one", page.locator("#strip .frame").count() == 3)
    check("the status is ready again", page.inner_text("#status") == "Ready", page.inner_text("#status"))
    check("Kodak is the default theme", page.evaluate("document.documentElement.dataset.theme") == "kodak")
    page.click("#theme-toggle")
    page.get_by_role("menuitemradio", name="Darkroom").click()
    check("Darkroom clears the theme", page.evaluate("document.documentElement.dataset.theme") is None)
    check_contrast(page, "Darkroom dark")
    page.emulate_media(color_scheme="light")
    time.sleep(0.5)
    page.screenshot(path=OUT + "4-light.png")
    check_contrast(page, "Darkroom light")
    page.emulate_media(color_scheme="dark")

    page.click("#theme-toggle")
    themes = page.locator("#theme-menu [role=menuitemradio]").all_inner_texts()
    check(
        "the theme menu offers four",
        themes == ["Darkroom", "Leica M", "Kodak Instamatic", "Polaroid SX-70"],
        str(themes),
    )
    page.keyboard.press("Escape")
    darkroom = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--chrome')")
    for name, slug in (("Leica M", "leica"), ("Kodak Instamatic", "kodak"), ("Polaroid SX-70", "polaroid")):
        page.click("#theme-toggle")
        page.get_by_role("menuitemradio", name=name).click()
        chrome = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--chrome')")
        check(f"{name} sets its theme", page.evaluate("document.documentElement.dataset.theme") == slug)
        check(f"{name} changes the chrome", chrome != darkroom, chrome)
        check_contrast(page, name)
        time.sleep(0.4)
        page.screenshot(path=OUT + f"4-theme-{slug}.png")
    for name, slug, expected in (
        ("Darkroom", "", "sweep"),
        ("Leica", "leica", "develop"),
        ("Kodak", "kodak", "rise"),
        ("Polaroid", "polaroid", "drop"),
    ):
        page.evaluate(f"document.documentElement.dataset.theme = '{slug}'")
        shape = page.evaluate(EXPOSURE)
        check(f"{name} makes the photo by a {expected}", shape["kind"] == expected, str(shape))
    page.evaluate("document.documentElement.dataset.theme = 'polaroid'")
    fresh = page.context.new_page()
    fresh.goto(f"http://127.0.0.1:{PORT}/")
    check("a new tab keeps the theme", fresh.evaluate("document.documentElement.dataset.theme") == "polaroid")
    fresh.close()
    page.click("#theme-toggle")
    page.get_by_role("menuitemradio", name="Darkroom").click()
    fresh = page.context.new_page()
    fresh.goto(f"http://127.0.0.1:{PORT}/")
    check("a new tab keeps Darkroom", fresh.evaluate("document.documentElement.dataset.theme") is None)
    fresh.close()
    for frame in page.locator("#strip .frame").all():
        frame.click()
        if page.inner_text(".prompt-line").startswith("A ceramic teapot"):
            break
    check("a caption that fits is plain text", page.get_attribute(".prompt-line", "role") is None)
    page.set_viewport_size({"width": 390, "height": 844})
    time.sleep(0.5)
    width = page.evaluate("document.documentElement.scrollWidth")
    check("phone has no sideways scroll", width <= 390, str(width))
    rows = page.evaluate("""() => [...document.querySelectorAll('.facts span:not(.break)')]
        .map(fact => [fact.innerText, Math.round(fact.getBoundingClientRect().top)])""")
    seed = next(index for index, (text, _) in enumerate(rows) if text.startswith("Seed"))
    check(
        "a phone puts the facts on two lines: which image, then how",
        # The badge's border and padding lift its top a few pixels on the same line.
        abs(rows[0][1] - rows[seed][1]) <= 4 and rows[seed + 1][1] == rows[-1][1] > rows[seed][1] + 8,
        str(rows),
    )
    caption = page.locator(".prompt-line")
    check("a caption the phone cuts becomes a toggle", caption.get_attribute("aria-expanded") == "false")
    print_box = page.locator(".pic").bounding_box()
    caption.click()
    check(
        "a click opens the whole prompt over the print",
        caption.get_attribute("aria-expanded") == "true"
        and page.inner_text(".sheet dd").startswith("A ceramic teapot")
        and "Overcast sky" in page.inner_text(".sheet"),
        page.inner_text(".sheet"),
    )
    check("the print does not move", page.locator(".pic").bounding_box() == print_box)
    check("focus goes to Close", page.evaluate("document.activeElement.getAttribute('aria-label')") == "Close")
    page.keyboard.press("Escape")
    check(
        "Escape closes it and gives focus back to the label",
        page.locator(".sheet").count() == 0
        and caption.get_attribute("aria-expanded") == "false"
        and page.evaluate("document.activeElement.classList.contains('prompt-line')"),
    )
    caption.press("Enter")
    check("Enter opens it", page.locator(".sheet").count() == 1)
    page.get_by_role("button", name="Close").click()
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
