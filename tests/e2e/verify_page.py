"""Real-run check of the page against a live studio server on the qwen21 backend.

It generates and edits real images, so it takes minutes. Screenshots go to a
temporary directory, printed at the start.

Every binding is a role, an accessible name, a label association, or an id the
page publishes. None is a decorative class name, so a change to how the page is
drawn does not move the assertion. Four kinds of binding are left, and each is
marked in place with `LEFT:` and a reason:

  - the page's own state, which it publishes as a global. No DOM reading makes
    the same claim, and the design's contract does not name the state.
  - geometry and computed style: where a box sits, and which custom property it
    carries. A role has no position.
  - an element with no role at all: the magnifier, which the page hides from
    assistive technology on purpose; the line the drawing tools sit on, and the
    pencil loop the shown frame draws; the film frame's own numbers; and the
    thumbnail inside a frame, which a browser flattens because it is inside a
    button.
  - a text the assertion is about. The caption under the print and the summary
    line below it are read for their words, and binding one by those words would
    make the words the assertion is about the thing that finds it.

Thirteen ids the checks lean on are not in the design's contract list, and the
list should carry the two the checks depend on most: `#go-sub` and `#status`.
The rest are `#region-preview`, `#region-note`, `#region-field`, `#stage-bar`,
`#toasts`, `#incoming`, `#tier-sizes`, `#look`, `#look-values`, `#counter` and
`#backend-toggle`.

Usage: uv run --with playwright python tests/e2e/verify_page.py <port>
"""

import base64
import io
import json
import re
import sys
import tempfile
import time
import urllib.parse

from PIL import Image
from playwright.sync_api import sync_playwright

PORT = sys.argv[1]
OUT = tempfile.mkdtemp(prefix="studio-e2e-") + "/"
print("Screenshots:", OUT)
results = []

# The verbs the run button uses to say whether a run is in flight, and the state
# it publishes beside them. The page shows one label at a time by setting
# `hidden` on the others, so the words survive a stylesheet that fails to load;
# the attribute carries the state itself, for a check that needs the state rather
# than the wording.
RUNNING = re.compile(r"^Cancel$")
STOPPING = re.compile(r"^Stopping")
RUN_IDLE = "#go[data-state='idle']"
RUN_STOPPING = "#go[data-state='stopping']"
# A kept frame names itself, and the mode it was made in, in its aria-label.
FRAME = re.compile(r"^(generate|edit), seed ")
# The badge that carries the weights, found by the title the contract keeps.
BADGE = "[title='The weights loaded']"
# The drawing tools, each of which names itself.
BRUSH = re.compile(r"^Brush width")
# How long a prompt rewrite may take. The qwen21 rewriter is a fine-tuned 9B model
# measured 2026-09-27 at 22 to 32 seconds per answer, and its first use in a
# process also loads 18.84 GB of weights. Two minutes is about four times the
# measured answer and leaves room for that load. A wait sized for the stub is a
# wait that fails on the engine this check exists for.
# See the module docstring and MAX_TOKENS in gateways/qwen21/rewriter.py.
REWRITE_TIMEOUT = 120000


def check(name, passed, detail=""):
    results.append((name, bool(passed), detail))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def leave_blocked(page):
    return page.evaluate("""() => {
        const event = new Event('beforeunload', { cancelable: true });
        window.dispatchEvent(event);
        return event.defaultPrevented;
    }""")


def parse_post(request):
    """One posted form, as a plain dict of single values."""
    return {name: values[0] for name, values in urllib.parse.parse_qs(request.post_data or "").items()}


def mask_size(b64):
    return Image.open(io.BytesIO(base64.b64decode(b64))).size


def mask_carries(b64, colour, tolerance=12):
    """A region reaches the model in the palette colour that names it."""
    image = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    hits = sum(
        1
        for pixel in image.resize((image.width // 4, image.height // 4)).getdata()
        if all(abs(pixel[channel] - colour[channel]) < tolerance for channel in range(3))
    )
    return hits > 5


def mask_colour_pixels(b64, colour, tolerance=12):
    """How many pixels of the mask carry one palette colour.

    That is the area the stroke painted, so two strokes of the same length painted
    at different widths count apart. The mask is what the model receives, so this
    is the width claim itself and not the page's bookkeeping about it.
    """
    image = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    return sum(
        1 for pixel in image.getdata() if all(abs(pixel[channel] - colour[channel]) < tolerance for channel in range(3))
    )


def set_brush(brush, width):
    """Put the brush on a named width, by the label the button carries.

    The brush is one button cycling three widths, so the wanted one is reached
    from wherever it is now. Three clicks is a full cycle: a label that never
    arrives leaves the later check to fail on the width it did find.
    """
    wanted = "Brush width: " + width
    for _ in range(3):
        if brush.get_attribute("aria-label") == wanted:
            return
        brush.click()


# The palette in the page, as channels, plus black. The strokes already carry
# these colours, so the snap only repairs the antialiased edge: a mask whose tones
# stay inside this set is the only thing that shows the snap ran at all.
MARK_PALETTE = {(0, 0, 0), (226, 118, 30), (226, 56, 31), (47, 158, 79), (47, 111, 224)}


def mask_tones(b64):
    """Every distinct RGB in the mask, at full size."""
    return set(Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB").getdata())


def mask_alpha(b64):
    """Every distinct alpha in the mask. The threshold writes one value."""
    return set(Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA").getchannel("A").getdata())


def wait_idle(page):
    """Wait for a run to be over.

    The run is over when the run button publishes `idle`. The attribute is what
    the page sets from the same place it toggles the body's `busy` class, and it
    is what this waits on rather than the button's words: the page shows one of
    its labels at a time, so waiting on the words ties the wait to a part of the
    button this check is not about. The wait is for `idle` and not for `busy` to
    go, because an attribute that stopped being published would then pass in
    silence.
    """
    page.locator(RUN_IDLE).wait_for(state="visible", timeout=600000)
    time.sleep(0.5)


def rewrite_prompt(page, button, typed):
    """Press the rewriter and take its answer off the wire.

    The answer is a second model's, so its wording cannot be asserted: the stub
    writes one sentence and the real rewriter writes the user a paragraph. The
    claim is that the page applied whatever came back, and the response is what
    makes that claim checkable on both engines. Both waits are the rewriter's own
    cost, which is minutes and not seconds.

    The route is matched exactly. The page polls `/rewrite/state` while a rewrite
    runs, and a substring match on `/rewrite` would take a poll's answer for the
    rewriter's.
    """
    with page.expect_response(lambda response: response.url.endswith("/rewrite"), timeout=REWRITE_TIMEOUT) as answer:
        button.click()
    body = json.loads(answer.value.text())
    page.wait_for_function(
        "(typed) => document.getElementById('prompt').value.trim() !== typed",
        arg=typed,
        timeout=REWRITE_TIMEOUT,
    )
    return body


def button(page, name):
    return page.get_by_role("button", name=name, exact=True)


def frames(page):
    """The kept frames, found by the label the page gives each one.

    A batch run holds a placeholder in the strip while it waits, and that
    placeholder names itself differently, so it is not a frame here.
    """
    return page.get_by_role("button", name=FRAME)


def shown_frame(page):
    """The frame on the stage, by the label the strip gives the frame it shows.

    The page holds the shown frame as an index of its own. The strip carries the
    same identity in the `aria-label` of the frame it marks selected, and that
    label is the one the design pins, so the claim reads from the DOM.
    """
    return page.locator("#strip .frame.selected").get_attribute("aria-label")


def set_phase(page, stage, step, total, label="", stopping=False):
    """Put the run into a phase, the way the server puts it there.

    The poll swaps a `.progress-state` element into `#progress`, and the page's
    own observer reads its attributes and repaints. So a check that needs a
    phase writes that element, which is the input the page already consumes, and
    the page draws itself. The element is replaced rather than rewritten, and
    the poller stays where it is: the observer watches for children, and taking
    the poller out would stop the run reporting.
    """
    page.evaluate(
        """([stage, step, total, label, stopping]) => {
             const slot = document.getElementById('progress');
             const old = slot.querySelector('.progress-state');
             const node = document.createElement('div');
             node.className = 'progress-state';
             node.dataset.stage = stage;
             node.dataset.step = step;
             node.dataset.total = total;
             node.dataset.label = label;
             node.dataset.stopping = stopping ? '1' : '0';
             if (old) old.replaceWith(node); else slot.append(node);
           }""",
        [stage, step, total, label, stopping],
    )


def toggle_look(page, row, label):
    """Open the Look row, then pick or unpick the option. A pick closes the row again.

    The row is named for itself and then its pick, and the stylesheet decides
    whether a space lands between the two: "Light none" with it, "Lightnone"
    without. The pattern therefore stops at the row's name, which is unambiguous
    because no chip label begins with the name of a row.
    """
    page.locator("#look-rows").get_by_role("button", name=re.compile(rf"^{re.escape(row)}")).click()
    page.locator("#look-rows").get_by_role("button", name=label, exact=True).click()


def region_rows(page):
    """One row per colour marked, each an instruction field for its area."""
    return page.locator("#region-rows").get_by_role("textbox")


def picked_looks(page):
    """The Look chips that are chosen.

    A pick closes its row, and a closed row is out of the accessibility tree, so
    the search keeps the hidden ones. A class query saw them whether or not the
    row was open, and this is the same claim.
    """
    return page.locator("#look-rows").get_by_role("button", pressed=True, include_hidden=True)


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
    # LEFT: a decorative class, and the claim is that it is absent.
    check("the top plate has no privacy line", page.locator(".topbar .privacy").count() == 0)
    check("the dial shows the weights", page.inner_text(BADGE) == "bf16")
    # LEFT: an id the page publishes, and the claim is that it is absent.
    check("the top plate has no frame counter", page.locator("#counter").count() == 0)
    # LEFT: `#status` is an id the page publishes, and it is not in the design's
    # contract. A live region that has nothing to say is not in the tree, so the
    # role would report the same thing for a hidden one and an empty one.
    check("the status is announced", page.get_attribute("#status", "aria-live") == "polite")
    # LEFT: `#go-sub` is an id the page publishes, and it is not in the design's
    # contract. The run button's own name carries the same words, but only with
    # the verb in front of them, which is a different claim about wording.
    check("the run button announces nothing", page.get_attribute("#go-sub", "aria-live") is None)
    # LEFT: the model's name is a span inside its button, and the top plate's
    # height is a length. Neither has a role, and a role has no height.
    page.evaluate("document.querySelector('#backend-toggle .name').textContent = 'A very long model name '.repeat(8)")
    name = page.evaluate("""() => {
        const name = document.querySelector('#backend-toggle .name');
        return [name.scrollWidth > name.clientWidth, document.querySelector('.topbar').offsetHeight];
    }""")
    check("a long model name truncates in the top plate", name == [True, 52], str(name))
    page.reload()
    # The readout is for a run. "Ready" said nothing, so it waits for one and goes with it.
    # LEFT: `#status` again, and the claim is that it is hidden.
    check("the top bar shows no status when idle", page.locator("#status").is_hidden())
    # The guide, which is the manual the studio did not have.
    check("no guide until it is asked for", page.locator("#guide-sheet").count() == 0)
    page.click("#guide-toggle")
    check(
        "the guide opens and lists what a person needs",
        page.locator("#guide-sheet dt").count() >= 6
        and page.get_attribute("#guide-sheet", "aria-label") == "How to use this studio",
        str(page.locator("#guide-sheet dt").count()),
    )
    check(
        "the guide says what a mark does",
        "Fill the area you want changed" in page.inner_text("#guide-sheet"),
        page.inner_text("#guide-sheet")[:60],
    )
    page.keyboard.press("Escape")
    check("Escape closes the guide", page.locator("#guide-sheet").count() == 0)
    button(page, "Browse templates").click()
    check("empty stage opens templates", page.locator("#templates").is_visible())
    page.keyboard.press("ArrowDown")
    # LEFT: focus is not a role, and the arrow key moves it to a menu item.
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
    page.get_by_role("button", name="4:3", exact=True).click()
    # The tiers of a shape are named for their megapixels, and the names follow the
    # shape, so the first one is found by its place under its own id. `#tier-sizes`
    # is an id the page publishes, and it is not in the design's contract.
    page.locator("#tier-sizes").get_by_role("button").first.click()
    page.click("#advanced summary")
    page.fill("#steps", "8")
    page.dispatch_event("#steps", "input")
    page.click("#count-toggle")
    check("a batch goes up to 4", page.locator("#count-menu [role=menuitemradio]").count() == 4)
    page.get_by_role("menuitemradio", name="2 images").click()
    check(
        "the count menu sets the count",
        # The button reads back the count it holds. `#count-shown` is the span inside
        # it, and the button is the contract id.
        page.locator("#count-toggle").inner_text().strip() == "×2"  # noqa: RUF001 (the multiplication sign)
        and page.input_value("#count") == "2",
        page.locator("#count-toggle").inner_text(),
    )
    # LEFT: the details that holds the Look rows is an id the page publishes, and
    # its summary is not a role a browser exposes. The rows inside are found by
    # role, and they are only visible once this has opened the details.
    page.click("#look summary")
    toggle_look(page, "Light", "Overcast")
    page.focus("#prompt")
    page.keyboard.press("Meta+Enter")
    # LEFT: the progress card's percentage is a span, and the card is the page's
    # own drawing of a run. It has no role.
    page.wait_for_selector(".card .percent:not(:empty)", timeout=300000)
    check("Cmd+Enter starts a run", True)
    # Before the first step the estimate is the only number and it never moves, so the
    # reading phase says how long it has been reading instead: a slow engine then looks
    # alive rather than frozen.
    # The phase is set the way the server sets it, as the `.progress-state`
    # element the poll swaps in, so the page repaints from its own observer and
    # nothing here calls the page's drawing. The run's start is the page's own
    # state and the run button publishes it, so that is where a check that needs
    # the page 95 seconds into its reading phase writes it.
    page.evaluate("() => { document.getElementById('go').dataset.started = String(Date.now() - 95000); }")
    set_phase(page, "running", 0, 20)
    reading = page.inner_text("#status")
    check(
        "the reading phase counts the time it has been reading",
        reading.startswith("Reading the") and "min" in reading and "so far" in reading,
        reading,
    )
    # A stop that has not landed yet says when it will, because an engine inside this
    # process can only stop where it looks, and before the first step there is nothing.
    # The body's class is the page's own state for a stop, and writing the
    # phase again is what a poll does, so the page repaints with the class on.
    page.evaluate("() => { document.body.classList.add('stopping'); }")
    set_phase(page, "running", 0, 20)
    check(
        "a stop before the first step says when it lands",
        page.inner_text("#status").startswith("Stopping when the first step arrives"),
        page.inner_text("#status"),
    )
    # The same phase, one step further on.
    set_phase(page, "running", 3, 20)
    check(
        "a stop after a step says it lands at the end of that step",
        page.inner_text("#status").startswith("Stopping at the end of this step"),
        page.inner_text("#status"),
    )
    page.evaluate("() => { document.body.classList.remove('stopping'); }")
    # The percent shows at 0% while the backend still loads, before step 1.
    page.wait_for_function("document.getElementById('status').innerText.startsWith('Step ')", timeout=300000)
    status = page.inner_text("#status")
    check("the status reads the step", status.startswith("Step ") and " of " in status, status)
    # LEFT: the print rising out of the bottom edge is a length, and the plate and
    # the bar are the page's own drawing of a run.
    bar = page.evaluate("""() => {
        const plate = document.querySelector('.card .plate').getBoundingClientRect();
        const bar = document.querySelector('.card .exposure').getBoundingClientRect();
        return [Math.round(plate.bottom - bar.bottom), bar.height / plate.height];
    }""")
    check("the Kodak print rises from the bottom edge", bar[0] == 0 and bar[1] < 0.5, str(bar))
    # LEFT: the same drawing, held across a mode switch to see that it is the same node.
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
        page.is_enabled("#go") and page.get_by_role("button", name=RUNNING).count() == 1,
        page.get_by_role("button", name=RUNNING).inner_text(),
    )
    check("the run button shows no step text", page.inner_text("#go-sub") == "", page.inner_text("#go-sub"))
    # LEFT: the fill bar has no role, and the claim is that it is absent.
    check("the run button has no fill bar", page.locator("#go .fill").count() == 0)
    # LEFT: the card is the page's own drawing of a run, and has no role.
    check(
        "the card keeps only the plate and the percentage",
        page.locator(".card [data-slot], .card .btn").count() == 0 and page.locator(".card .percent").count() == 1,
    )
    page.keyboard.press("Meta+Enter")
    time.sleep(1)
    # LEFT: the chain placeholder is the page's own mark for a request in flight.
    check("Cmd+Enter while running sends nothing", page.locator("#incoming .chain").count() <= 1)
    page.focus("#seed")
    page.keyboard.press("Enter")  # an implicit submit clicks the run button, which is Cancel's guard
    time.sleep(1)
    # LEFT: the chain placeholder again.
    check("Enter in a field while running sends nothing", page.locator("#incoming .chain").count() <= 1)
    check(
        "Enter in a field does not cancel either",
        # The run button publishes its state, and a cancel would put it in
        # `stopping`. This is the attribute and not the button's words, for the
        # same reason `wait_idle` is.
        page.locator(RUN_STOPPING).count() == 0,
    )
    time.sleep(1)
    page.screenshot(path=OUT + "1-running.png")
    # The run button publishes its state, and item 10 of what must not move pins
    # it. A page from before that change has none, and every wait below would
    # hang for ten minutes rather than say so. Raised rather than asserted,
    # because `python -O` drops an assert and the hang would come back silently.
    if page.locator("#go[data-state]").count() != 1:
        raise AssertionError(
            "#go publishes no data-state. Item 10 of 'what must not move' pins that "
            "attribute, and a page from before that change does not have it."
        )
    wait_idle(page)
    check("2 images in the strip", frames(page).count() == 2)
    go_box = page.locator("#go").bounding_box()
    check(
        "run button in view with images",
        go_box["y"] + go_box["height"] <= 900 and page.evaluate("document.documentElement.scrollHeight") <= 900,
        f"bottom {go_box['y'] + go_box['height']:.0f}",
    )
    check("no leave warning while the browser keeps the images", not leave_blocked(page))
    # LEFT: the line a run is summarised in is the page's own drawing of a frame,
    # with no role. The frame's own name carries the seed and the size.
    check("a plain run says Generated", page.inner_text(".facts .made") == "Generated", page.inner_text(".facts .made"))
    # LEFT: the page's own state: the rate it learned for the shape it just ran.
    learned = page.evaluate("() => learnedCost[costKey()] || 0")
    check("a run teaches the step rate", 0.3 < learned < 20, f"{learned:.2f} s per step at 1 MP")
    # LEFT: the caption is the only place the reader sees the whole prompt, and it
    # has no role until it is long enough to be cut. Binding it by its own text
    # would make the text the assertion is about the very thing that finds it.
    check(
        "the caption shows the typed prompt, then the Look muted",
        page.inner_text(".prompt-line").startswith(
            "A ceramic teapot on a linen tablecloth, soft window light from the left. Overcast"
        )
        and page.inner_text(".prompt-line .look-said").startswith("Overcast"),
        page.inner_text(".prompt-line"),
    )
    # LEFT: the summary line again, and the claim is about the spans in it.
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
        picked_looks(page).all_text_contents() == ["Overcast"]
        and page.input_value("#prompt").startswith("A ceramic teapot"),
    )
    toggle_look(page, "Light", "Overcast")
    check("tab title back to normal", page.title() == "Qwen-Image-2.1", page.title())
    time.sleep(1)
    page.screenshot(path=OUT + "2-result.png")

    # Film frame and pencil mark
    # LEFT: the film frame's strip of numbers, and which frame the stage shows.
    # Neither has a role, and the strip carries no aria-current.
    check(
        "image sits in a film frame with its number",
        page.locator(".shot .edge").inner_text().endswith(page.locator("#strip .frame.selected .no").inner_text()),
        page.locator(".shot .edge").inner_text(),
    )
    frames(page).nth(1).click()
    # LEFT: the pencil loop is an SVG drawn inside the shown frame, with no role.
    check("picking a frame draws the pencil loop", page.locator("#strip .frame.selected .mark.draw").count() == 1)
    # The strip draws its frames again whenever the gallery it reads changes, and
    # picking the frame already on the stage is one of those times: the page
    # shows it again and the element draws its tree again. The loop belongs to
    # the pick, so the second draw does not repeat it.
    frames(page).nth(1).click()
    check(
        "a redraw does not draw it again",
        page.locator("#strip .frame.selected .mark.draw").count() == 0
        and page.locator("#strip .frame.selected .mark").count() == 1,
    )
    frames(page).nth(0).click()

    # LEFT: the thumbnail is an image inside the frame's own button, and a browser
    # flattens what is inside a button, so it carries no role. The frame is found
    # by role; only the image inside it is found by its tag.
    thumb = frames(page).nth(0).locator("img").element_handle()
    frames(page).nth(1).click()
    frames(page).nth(0).click()
    check("the strip keeps its thumbnails", page.evaluate("(img) => img.isConnected", thumb))
    check("thumbnails use blob URLs", page.evaluate("(img) => img.src.startsWith('blob:')", thumb))

    # Reduced motion: nothing animates. Both names are read off the frames the
    # strip really drew, and not off a probe built in the page. A probe passes
    # even if the component stops emitting the classes. The probe this replaces
    # read `MARK`, the page's own copy of the loop, out of the global scope, and
    # slice 8 moved that markup into `components/image-strip.js`, so the global
    # it read no longer existed. Two picks, so the second frame carries the loop
    # the pick draws, and the first frame keeps the entrance it arrived with.
    frames(page).nth(1).click()
    frames(page).nth(0).click()
    page.emulate_media(reduced_motion="reduce")
    # LEFT: the loop is an SVG inside the shown frame, and its class is what
    # carries the animation, so no role reaches it.
    animated = page.evaluate("""() => {
        const frame = document.querySelector('#strip .frame.arrive');
        const loop = document.querySelector('#strip .frame.selected .mark.draw path');
        return [frame, loop].map(el => el ? getComputedStyle(el).animationName : 'not drawn');
    }""")
    check("reduced motion stops every animation", all(name == "none" for name in animated), str(animated))
    page.emulate_media(reduced_motion="no-preference")
    # The same frame with motion allowed, so a page that animates nothing at all
    # cannot pass the check above.
    normal = page.evaluate("""() => {
        const frame = document.querySelector('#strip .frame.arrive');
        return frame ? getComputedStyle(frame).animationName : 'not drawn';
    }""")
    check("normal motion animates", normal == "join", normal)

    # The left column keeps its width whatever the strip holds. It used to lose
    # that width to the strip's content, which pushed the stage, the print and
    # the caption over the controls at the right. Filling the strip with 16:9
    # images takes ten runs, and the content's width is the whole trigger, so
    # the frames are cloned at a wide thumbnail's width instead.
    # LEFT: a clone of the strip's own nodes, at a width the page has no role for.
    page.evaluate("""() => {
        const strip = document.querySelector('#strip');
        const frames = Array.from(strip.querySelectorAll('.frame'));
        for (let i = 0; i < 14; i++) {
            const copy = frames[i % frames.length].cloneNode(true);
            copy.classList.add('clone');
            copy.querySelector('.still').style.width = '106px';
            strip.append(copy);
        }
    }""")
    # LEFT: two scroll widths and two box edges, none of which is a role.
    check(
        "a full strip scrolls instead of widening the column",
        page.evaluate("""() => {
            const strip = document.querySelector('#strip');
            const stage = document.querySelector('.stage').getBoundingClientRect();
            const panel = document.querySelector('form').getBoundingClientRect();
            return strip.scrollWidth > strip.clientWidth + 1 && stage.right <= panel.left + 1;
        }"""),
    )
    page.evaluate("() => document.querySelectorAll('#strip .frame.clone').forEach((node) => node.remove())")

    # The shown frame is read from the strip's own label for it, so the check
    # binds to the accessible name the design pins and not to a page global.
    page.mouse.click(200, 200)
    first = shown_frame(page)
    page.keyboard.press("ArrowRight")
    check("ArrowRight steps outside full screen", shown_frame(page) != first)
    page.keyboard.press("ArrowLeft")
    check("ArrowLeft steps back outside full screen", shown_frame(page) == first)

    # Full screen
    page.keyboard.press("f")
    time.sleep(0.5)
    # LEFT: the element the browser hands to full screen is the page's own pane,
    # and the browser reports it as a node rather than as a role.
    check("F enters full screen", page.evaluate("document.fullscreenElement === document.querySelector('.work')"))
    first = shown_frame(page)
    page.keyboard.press("ArrowRight")
    check("ArrowRight shows the next frame", shown_frame(page) != first)
    page.keyboard.press("ArrowLeft")
    check("ArrowLeft goes back", shown_frame(page) == first)
    page.screenshot(path=OUT + "2b-fullscreen.png")
    # The binding here is a role with a name, and it resolves without the
    # stylesheet. The reach does not: with the stylesheet refused, the fullscreen
    # pane is fixed at 900 and cannot scroll, and this button sits at y 1908 in
    # it, so no click can land. The cascade is what puts the control in reach.
    button(page, "Exit full screen (F)").click()
    time.sleep(0.5)
    check("the button leaves full screen", page.evaluate("document.fullscreenElement === null"))

    page.get_by_role("button", name="More actions").click()
    check("More menu opens", page.locator("#more-menu").is_visible())
    page.mouse.click(200, 200)
    check("outside click closes More", page.locator("#more-menu").is_hidden())

    # Edit this
    button(page, "Edit this").click()
    check("Edit this switches to edit", page.get_by_role("radio", name="Edit").is_checked())
    check("Edit this leaves one reference", page.locator("#thumbs").get_by_role("img").count() == 1)
    check("Edit this clears the prompt", page.input_value("#prompt") == "")
    # LEFT: the summary line again.
    seed = page.locator(".facts span", has_text="Seed").first.inner_text().split()[-1]
    check("Edit this keeps the seed", page.input_value("#seed") == seed, seed)
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Use as reference").click()
    check("Use as reference adds a second", page.locator("#thumbs").get_by_role("img").count() == 2)
    # LEFT: the film frame's numbers again.
    source = page.inner_text(".shot .edge span:last-child")
    button(page, "Edit this").click()
    check("Edit this resets to one", page.locator("#thumbs").get_by_role("img").count() == 1)

    # One-image edit and the compare slider
    page.fill("#prompt", "Change only the teapot's color to glossy cobalt blue. Keep everything else unchanged.")
    page.dispatch_event("#prompt", "input")
    page.get_by_role("button", name="0.3 MP", exact=True).click()
    page.click("#count-toggle")
    page.get_by_role("menuitemradio", name="1 image").click()
    # Record every split value from the run on, so the check sees the whole
    # sweep instead of racing it with a fixed-time sample.
    # LEFT: the divider's own custom property, sampled frame by frame.
    page.evaluate(
        "window.splits = []; (function sample() {"
        " const pic = document.querySelector('.pic');"
        " const split = pic && pic.style.getPropertyValue('--split');"
        " if (split && split !== window.splits[window.splits.length - 1]) window.splits.push(split);"
        " requestAnimationFrame(sample); })()"
    )
    before = frames(page).count()
    page.click("#go")
    wait_idle(page)
    # The run's own answer is the frame that arrives, and the summary line
    # describes the frame the stage shows. A run that answers nothing, an engine
    # error or a refused edit, leaves the stage on the frame before it, whose
    # summary reads "Generated". So the summary alone cannot tell an edit that
    # answered from an edit that never arrived: it would report a mode the page
    # never posted. Three claims make that impossible. The frame count says the
    # run answered. The stage says it holds a frame, which only a draw of an
    # entry does: the bar and its summary outlive a draw that had no entry to
    # make, so a summary can be read off the frame before without this. And the
    # toast is what the page said when the run answered nothing. It carries the
    # reason for an engine error until it is dismissed, and for four seconds when
    # it reports a stop.
    arrived = frames(page).count()
    shots = page.locator(".shot").count()
    # LEFT: the print's own frame, which has no role, and the summary line again.
    made = page.inner_text(".facts .made")
    check(
        "the edit answers a frame, the stage shows it, and it names its source",
        arrived == before + 1 and shots == 1 and made == f"Edited from {source}",
        f"{before} frames before, {arrived} after; the stage shows {shots}; "
        f"the summary says {made!r}; the page says: "
        + (page.locator("#toasts").inner_text().strip().replace("\n", " ") or "nothing"),
    )
    page.get_by_role("button", name=f"Show frame {source}").click()
    # LEFT: the film frame's numbers again.
    check("the source link shows that frame", page.inner_text(".shot .edge span:last-child") == source)
    frames(page).nth(0).click()
    check(
        "compare slider on the edit",
        page.get_by_label("Compare before and after").count() == 1
        and page.get_by_role("img", name="The image before the edit").count() == 1,
    )
    time.sleep(2)
    splits = [float(value.rstrip("%")) for value in page.evaluate("window.splits")]
    check(
        "the divider sweeps in once",
        splits[:1] == [0] and splits[-1:] == [50] and splits == sorted(splits),
        str(splits),
    )
    page.screenshot(path=OUT + "3-compare.png")
    # LEFT: the print's own box, and the tags drawn in its corners. A role has no
    # position, and the tags are spans with no role.
    pic = page.locator(".pic").bounding_box()
    tag = page.locator(".compare-tag.left").bounding_box()
    check(
        "tags sit on the image",
        pic["x"] <= tag["x"] <= pic["x"] + 20 and pic["y"] <= tag["y"] <= pic["y"] + 20,
        f"pic {pic['x']:.0f},{pic['y']:.0f} tag {tag['x']:.0f},{tag['y']:.0f}",
    )
    box = page.get_by_label("Compare before and after").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.2, box["y"] + box["height"] / 2)
    # LEFT: the divider's own custom property.
    split = page.evaluate("getComputedStyle(document.querySelector('.pic')).getPropertyValue('--split').trim()")
    check("a click moves the split", split in ("19%", "20%", "21%"), split)
    compare = page.get_by_role("button", name="Compare")
    compare.click()
    check(
        "Compare off shows the result alone",
        page.get_by_label("Compare before and after").count() == 0
        and compare.get_attribute("aria-pressed") == "false"
        and compare.evaluate("el => el === document.activeElement"),
    )
    compare.click()
    check("Compare on brings the slider back", page.get_by_label("Compare before and after").count() == 1)
    frames(page).nth(1).click()
    check("no slider on a generate image", page.get_by_label("Compare before and after").count() == 0)
    check("no Compare switch on a generate image", compare.count() == 0)
    frames(page).nth(0).click()
    check(
        "second view opens at the middle",
        # LEFT: the divider's own custom property.
        page.evaluate("getComputedStyle(document.querySelector('.pic')).getPropertyValue('--split').trim()") == "50%",
    )

    # Two-image edit: no slider
    frames(page).nth(1).click()
    button(page, "Edit this").click()
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Use as reference").click()
    page.fill("#prompt", "Put the two teapots side by side on one table.")
    page.dispatch_event("#prompt", "input")
    check("a two-image edit holds both references", page.locator("#thumbs").get_by_role("img").count() == 2)
    page.click("#go")
    wait_idle(page)
    check(
        "no slider on a two-image edit",
        page.get_by_label("Compare before and after").count() == 0,
    )

    # Mode switch and cancel
    check(
        "edit shows no Look, since qwen21 declares none for it",
        page.locator("#look-rows").get_by_role("button").count() == 0,
    )
    page.click("label[for=mode-generate]")
    toggle_look(page, "Light", "Overcast")
    page.click("label[for=mode-edit]")
    page.click("label[for=mode-generate]")
    check(
        "mode switch clears the look",
        picked_looks(page).count() == 0
        # LEFT: the read-back the summary prints, an id the page publishes.
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
    check(
        "a click in the first half second does not cancel",
        page.locator(RUN_STOPPING).count() == 0,
    )
    # LEFT: the progress card's percentage again.
    page.wait_for_selector(".card .percent:not(:empty)", timeout=300000)
    page.click("#go")
    check(
        "Cancel reads Stopping while it stops",
        page.get_by_role("button", name=STOPPING).count() == 1,
        page.get_by_role("button", name=STOPPING).inner_text(),
    )
    wait_idle(page)
    check("cancel ends the run, no new image", frames(page).count() == 4)

    # Remove, themes, phone
    frames(page).nth(0).click()
    page.get_by_role("button", name="Remove", exact=True).click()
    check("remove takes one", frames(page).count() == 3)

    # A marked region: the page draws it on the print, the run carries it as the
    # last image whose areas are the marked colours, and the prompt is written from
    # the per area rows. The tool appears only where the mode declares a region.
    page.get_by_role("button", name="Edit this", exact=True).click()
    # The reference's size is read first, so the mark arrives a moment after the click.
    mark = page.get_by_label("Mark the area to change")
    mark.wait_for(state="visible", timeout=10000)
    check(
        "an edit starts with the brush armed",
        # LEFT: the line the tools sit on is a div with no role, so only the mark
        # canvas, which carries a label, is found by one.
        mark.count() == 1 and page.locator(".stage-bar .region-tools").count() == 1,
    )
    check(
        "the drawing tools take their own line, undo dead until a mark exists",
        # LEFT: the line the tools take is a div with no role, and the count is of
        # the buttons in it. Counting the ones that name themselves would miss a
        # tool added under a new name, which is exactly what this number guards.
        page.locator(".stage-bar .region-tools button").count() == 7
        and page.get_by_role("button", name="Take back the last mark").is_disabled(),
    )
    # LEFT: where two lines sit against each other is a length, and a role has none.
    check(
        "the controls line sits at the right, above the buttons there",
        page.evaluate("""() => { const tools = document.querySelector('.region-tools').getBoundingClientRect();
            const actions = document.querySelector('.stage-bar .actions').getBoundingClientRect();
            return Math.abs(tools.right - actions.right) < 4; }"""),
    )
    # LEFT: the same, against the caption's own box.
    check(
        "their line is between the picture and its caption",
        page.evaluate("""() => { const tools = document.querySelector('.region-tools').getBoundingClientRect();
            const caption = document.querySelector('.prompt-line').getBoundingClientRect();
            const actions = document.querySelector('.stage-bar .actions').getBoundingClientRect();
            return tools.bottom <= caption.top + 1 && tools.width >= caption.width
                && actions.top >= caption.top - 1; }"""),
    )

    # The model repaints the area the mark covers, so the brush's width is the
    # precision the user has. The width is on the button's own label, and the
    # width a stroke keeps is measured on the mask at the run below, because the
    # mask is what the model receives.
    brush = page.get_by_role("button", name=BRUSH)
    set_brush(brush, "thin")
    cycle = [brush.get_attribute("aria-label")]
    for _ in range(3):
        brush.click()
        cycle.append(brush.get_attribute("aria-label"))
    check(
        "the brush button cycles three widths and comes back", len(set(cycle)) == 3 and cycle[0] == cycle[3], str(cycle)
    )
    set_brush(brush, "medium")

    # The loupe: up while a stroke is drawn, holding the print, and gone when it ends.
    # LEFT: the magnifier is hidden from assistive technology on purpose, so it
    # carries no role and no name by design. Its pixels and its box are the claim.
    overlay = mark.bounding_box()
    loupe = page.locator(".shot .region-loupe")
    check("no loupe while nothing is drawn", not loupe.is_visible())
    page.mouse.move(overlay["x"] + 100, overlay["y"] + 130)
    page.mouse.down()
    page.mouse.move(overlay["x"] + 170, overlay["y"] + 190, steps=4)
    check(
        "the loupe is up while a stroke is drawn, and holds the print",
        loupe.is_visible()
        and loupe.evaluate("""(l) => {
            const d = l.getContext('2d').getImageData(0, 0, l.width, l.height).data;
            let lit = 0;
            for (let i = 0; i < d.length; i += 4) if (d[i] + d[i + 1] + d[i + 2] > 60) lit += 1;
            return lit > 500; }"""),
    )
    page.mouse.up()
    check("the loupe goes when the stroke ends", not loupe.is_visible())
    # Drawn near the print's own edge, so the clamping has something to do.
    page.mouse.move(overlay["x"] + overlay["width"] - 12, overlay["y"] + overlay["height"] - 12)
    page.mouse.down()
    page.mouse.move(overlay["x"] + overlay["width"] - 6, overlay["y"] + overlay["height"] - 6, steps=3)
    check(
        "the loupe stays inside the print, even at its corner",
        loupe.evaluate("""(l) => {
            const box = l.getBoundingClientRect();
            const print = document.querySelector('.shot .pic').getBoundingClientRect();
            return box.right <= print.right + 1 && box.bottom <= print.bottom + 1
                && box.left >= print.left - 1; }"""),
    )
    page.mouse.up()
    check(
        "the note says the whole marked area is repainted",
        # LEFT: the note is a paragraph with an id the page publishes.
        "whole marked area is repainted" in page.inner_text("#region-note"),
        page.inner_text("#region-note"),
    )
    page.get_by_role("button", name="Clear every mark").click()

    # The template names the region, so a row is a second way to say the same thing rather
    # than the only way, and an empty row writes nothing instead of leaving a clause with
    # no instruction in it.
    page.click("#templates-toggle")
    page.get_by_role("menuitem", name="Mark a region").click()
    page.keyboard.type("turn the wall blue")
    check(
        "the region template waits for a region",
        page.inner_text("#go-sub") == "Draw the region this prompt names",
        page.inner_text("#go-sub"),
    )
    page.mouse.move(overlay["x"] + 90, overlay["y"] + 110)
    page.mouse.down()
    page.mouse.move(overlay["x"] + 150, overlay["y"] + 170, steps=4)
    page.mouse.up()
    # LEFT: the sentence the page composes is printed in a paragraph the page
    # publishes, and it has no role. Binding it by that sentence would make the
    # sentence the assertion is about the very thing that finds it.
    preview = page.inner_text("#region-preview")
    check(
        "the template names the region, so the empty row writes nothing",
        not page.is_disabled("#go")
        and region_rows(page).count() == 1
        and "turn the wall blue in the area marked in <image2>" in preview
        and "area of <image2>" not in preview,
        preview,
    )
    page.get_by_role("button", name="Clear every mark").click()
    page.fill("#prompt", "")
    page.dispatch_event("#prompt", "input")
    # The mask is one more image, so the run costs more per step than the picture
    # alone. A learned rate covers the shape it came from, so it is cleared here:
    # this is about the backend's constants, which a new shape falls back to.
    # LEFT: the page's own state: the rate it learned, and the estimate that follows.
    page.evaluate("() => { Object.keys(learnedCost).forEach(function (key) { delete learnedCost[key]; }); }")
    before = page.evaluate("() => stepSeconds()")
    overlay = mark.bounding_box()
    # The first stroke is the thin one. The second, below, is drawn broad, so the
    # mask says whether each kept the width it was drawn with.
    set_brush(brush, "thin")
    page.mouse.move(overlay["x"] + 100, overlay["y"] + 120)
    page.mouse.down()
    page.mouse.move(overlay["x"] + 200, overlay["y"] + 220, steps=6)
    page.mouse.up()
    # The mark's own canvas, reached by the label it carries.
    covered = mark.evaluate("""(c) => {
        const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let white = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200) white += 1;
        return white; }""")
    check("drawing paints the print", covered > 100, str(covered))
    after = page.evaluate("() => stepSeconds()")
    # The mask is one more image, so the run costs more per step than the picture
    # alone. Measured 2026-09-27: it multiplies the step cost by about 1.175, so
    # the bar is a tenth rather than the third the old 0.6 constant implied.
    check(
        "the estimate counts the mask as one more image",
        before > 0 and after > before * 1.1,
        f"{before:.2f} s per step with no region, {after:.2f} with one",
    )
    check("one row per marked colour", region_rows(page).count() == 1)
    # The prompt field stays for a whole-picture instruction, which is only worth
    # asserting if what is typed in it reaches the sentence the page writes.
    page.fill("#prompt", "make it morning")
    page.dispatch_event("#prompt", "input")
    check(
        "an instruction about the whole picture leads the composed sentence",
        page.inner_text("#region-preview").startswith("make it morning"),
        page.inner_text("#region-preview")[:60],
    )
    page.fill("#prompt", "")
    page.dispatch_event("#prompt", "input")
    # The row offers an example instruction as its placeholder. The set the
    # example is drawn from is no longer published for a check to read: publishing
    # it for a test is a hook by another route. So the claim traded down from
    # membership of the set to the placeholder's own presence and shape.
    placeholder = region_rows(page).nth(0).get_attribute("placeholder")
    check(
        "the row offers an example instruction as its placeholder",
        placeholder.startswith("For example: ") and len(placeholder) > len("For example: "),
        placeholder,
    )
    region_rows(page).nth(0).fill("change the cloth to green")
    check(
        "the preview shows the sentence the page will send",
        "change the cloth to green in the orange area of <image2>" in page.inner_text("#region-preview"),
        page.inner_text("#region-preview")[-60:],
    )
    # The second stroke is drawn broad, where the first was thin. The mask below
    # says whether each kept the width it was drawn with.
    set_brush(brush, "broad")
    page.get_by_role("button", name="Mark in red").click()
    page.mouse.move(overlay["x"] + 240, overlay["y"] + 250)
    page.mouse.down()
    page.mouse.move(overlay["x"] + 330, overlay["y"] + 330, steps=6)
    page.mouse.up()
    check("a second colour adds its own row", region_rows(page).count() == 2)
    # The swatch colours the next mark and leaves the drawn one alone. The rows
    # are one per colour, in the palette's own order, so a swatch that repainted
    # the first stroke would leave one row and not two.
    check(
        "a swatch colours the next mark only",
        [row.get_attribute("aria-label") for row in region_rows(page).all()]
        == ["What changes in the orange area?", "What changes in the red area?"],
        str(page.locator("#region-rows").all_inner_texts()),
    )
    region_rows(page).nth(1).fill("to brass")
    check(
        "a fragment in a row stops the run with an example",
        page.inner_text("#go-sub").startswith("Write a whole instruction for the red area") and page.is_disabled("#go"),
        page.inner_text("#go-sub"),
    )
    # An instruction may open with a preposition and still be a whole one, so the
    # comma is what separates it from a bare phrase.
    region_rows(page).nth(1).fill("in the corner, add a lamp")
    check(
        "a whole instruction that opens with a preposition is not a fragment",
        not page.is_disabled("#go") and "Write a whole instruction" not in page.inner_text("#go-sub"),
        page.inner_text("#go-sub"),
    )
    region_rows(page).nth(1).fill("change the handle to brass")
    sent = {}
    page.on("request", lambda request: sent.update(parse_post(request)) if "/generate" in request.url else None)
    page.click("#go")
    wait_idle(page)
    references = json.loads(sent.get("references", "[]"))
    check("a marked run sends one more image", len(references) == 2, str(len(references)))
    check(
        "the mask carries each region's colour at the reference's size",
        mask_size(references[-1]) == mask_size(references[0])
        and mask_carries(references[-1], (226, 118, 30))
        and mask_carries(references[-1], (226, 56, 31)),
        f"size {mask_size(references[-1])} vs {mask_size(references[0])}, "
        f"orange {mask_carries(references[-1], (226, 118, 30))} red {mask_carries(references[-1], (226, 56, 31))}",
    )
    # The colours above are within a tolerance, so they pass whether or not the
    # snap ran: the strokes already carry them. These two do not.
    tones = mask_tones(references[-1])
    check(
        "the mask holds only the palette colours and black, with nothing between",
        tones <= MARK_PALETTE,
        f"outside the palette: {sorted(tones - MARK_PALETTE)[:6]}",
    )
    check(
        "the mask is fully opaque, so the threshold left no soft edge",
        mask_alpha(references[-1]) == {255},
        str(sorted(mask_alpha(references[-1]))),
    )
    # Each stroke kept the width it was drawn with: the first was drawn thin and
    # the second broad, and the mask holds the area each one painted. The strokes
    # are 100 and 90 client pixels long and a twentieth against an eighth of the
    # image wide, so the broad one paints about seven times the area. The bar is
    # a third of that, and a brush that repainted the first stroke would leave the
    # two counting alike.
    thin_pixels = mask_colour_pixels(references[-1], (226, 118, 30))
    broad_pixels = mask_colour_pixels(references[-1], (226, 56, 31))
    check(
        "each stroke keeps the width it was drawn with",
        thin_pixels > 0 and broad_pixels > thin_pixels * 2,
        f"{thin_pixels} px painted by the thin stroke, {broad_pixels} px by the broad one",
    )
    sent_prompt = sent.get("prompt", "")
    check(
        "the prompt names each area by its colour, and pins the rest",
        "<image2>" in sent_prompt
        and "in the orange area of" in sent_prompt
        and "in the red area of" in sent_prompt
        and "Keep the background and everything else unchanged" in sent_prompt,
        sent_prompt[-90:],
    )

    # A mark belongs to the picture it was drawn on, so the run's result took the
    # brush away. Bring it back on the frame the result came from.
    page.get_by_role("button", name="Edit this", exact=True).click()
    mark.wait_for(state="visible", timeout=10000)
    # A marked edit result is also the frame a divided view shows, and the divider
    # covers the whole print, so the two cannot both take the drag. The brush steps
    # the divided view aside rather than leaving a control that cannot be used.
    # LEFT: the divider itself is a div with an icon in it and no role.
    check(
        "the divided view steps aside while the brush is on the print",
        not page.get_by_label("Compare before and after").is_visible()
        and not page.locator(".shot .divider").is_visible()
        and mark.count() == 1,
    )
    overlay = mark.bounding_box()
    page.mouse.move(overlay["x"] + 120, overlay["y"] + 140)
    page.mouse.down()
    page.mouse.move(overlay["x"] + 240, overlay["y"] + 260, steps=6)
    page.mouse.up()
    region_rows(page).nth(0).fill("change the cloth to linen")
    check("a region is back, with its row", region_rows(page).count() == 1)

    # Clear recomputes the rows and both buttons, not only the strokes. The list on
    # screen and the buttons' own state both read the stroke count.
    page.get_by_role("button", name="Clear every mark").click()
    check(
        "Clear takes the rows and both buttons with it",
        region_rows(page).count() == 0
        # LEFT: `#region-field` is a container the page publishes with an id.
        and page.is_hidden("#region-field")
        and page.get_by_role("button", name="Take back the last mark").is_disabled()
        and page.get_by_role("button", name="Clear every mark").is_disabled(),
    )

    # The region token is the page's to fill, and it needs a region to fill it
    # with. Without one the run waits, rather than sending the token as text.
    page.fill("#prompt", "Change only the cloth in the area marked in [the region you marked].")
    page.dispatch_event("#prompt", "input")
    check(
        "the token with no region waits for one",
        page.inner_text("#go-sub") == "Draw the region this prompt names" and page.is_disabled("#go"),
        page.inner_text("#go-sub"),
    )
    page.mouse.move(overlay["x"] + 120, overlay["y"] + 140)
    page.mouse.down()
    page.mouse.move(overlay["x"] + 240, overlay["y"] + 260, steps=6)
    page.mouse.up()
    region_rows(page).nth(0).fill("change the cloth to linen")
    check(
        "the token becomes the mask's own image number",
        "[the region you marked]" not in page.inner_text("#region-preview")
        and "in the area marked in <image2>" in page.inner_text("#region-preview"),
        page.inner_text("#region-preview"),
    )
    page.click("#go")
    wait_idle(page)
    sent_prompt = sent.get("prompt", "")
    check(
        "the run carries no token",
        "[the region you marked]" not in sent_prompt and "in the area marked in <image2>" in sent_prompt,
        sent_prompt[-100:],
    )
    # The card holds the user's own words. Reading back the sentence the page
    # composed around the region rows is what made a run look rewritten.
    # LEFT: the caption again. It is a control once it is cut, so a role binding
    # would have to name the very words this reads back.
    caption = page.locator(".prompt-line").first.inner_text()
    check(
        "the card keeps the user's words, not the composed sentence",
        caption == "Change only the cloth in the area marked in [the region you marked]."
        and "Keep the background and everything else unchanged" not in caption,
        caption[-70:],
    )

    # A run with nothing in the prompt field. The row is then the only place the
    # change was asked for, so the card holds the sentence the page wrote for a
    # reader, without the number of the image carrying the mask.
    page.get_by_role("button", name="Edit this", exact=True).click()
    mark.wait_for(state="visible", timeout=10000)
    page.fill("#prompt", "")
    page.dispatch_event("#prompt", "input")
    overlay = mark.bounding_box()
    page.mouse.move(overlay["x"] + 120, overlay["y"] + 140)
    page.mouse.down()
    page.mouse.move(overlay["x"] + 240, overlay["y"] + 260, steps=6)
    page.mouse.up()
    region_rows(page).nth(0).fill("change the cloth to linen")
    page.click("#go")
    wait_idle(page)
    # LEFT: the caption again.
    caption = page.locator(".prompt-line").first.inner_text()
    check(
        "a rows-only run's card holds the sentence the page wrote, without the mask's number",
        "change the cloth to linen in the" in caption
        and "Keep the background and everything else unchanged" in caption
        and "<image" not in caption,
        caption[-90:],
    )

    # Reuse prompt hands back the user's own words. A rows-only run has none, and the
    # composed sentence is not the user's to edit, so the box comes back empty.
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Reuse prompt").click()
    check(
        "Reuse prompt hands back nothing when the run had no words of its own",
        page.input_value("#prompt") == "",
        repr(page.input_value("#prompt")),
    )

    # A mark belongs to its picture: leaving that picture drops it, says so, and
    # takes the row with it, so a region drawn again in that colour starts clean
    # instead of inheriting an instruction for a picture it was never about.
    page.get_by_role("button", name="Edit this", exact=True).click()
    mark.wait_for(state="visible", timeout=10000)
    overlay = mark.bounding_box()
    page.mouse.move(overlay["x"] + 120, overlay["y"] + 140)
    page.mouse.down()
    page.mouse.move(overlay["x"] + 240, overlay["y"] + 260, steps=6)
    page.mouse.up()
    region_rows(page).nth(0).fill("change the cloth to linen")
    frames(page).nth(1).click()
    check(
        "leaving the marked frame drops the mark, takes the row and says so",
        region_rows(page).count() == 0 and page.locator("#toasts").inner_text().strip() != "",
        str(page.locator("#region-rows").all_inner_texts()),
    )

    # Two references: the mask would mark a region of the first image while the
    # prompt names only the mask, and which picture owns the region is untested,
    # so the tool steps aside rather than guess.
    frames(page).first.click()
    page.get_by_role("button", name="Edit this", exact=True).click()
    mark.wait_for(state="visible", timeout=10000)
    check("the brush is back for the one-reference edit", mark.count() == 1)
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Use as reference").click()
    check("the brush steps aside with two references", mark.count() == 0)

    # Run empties the form, and Cancel puts it back. The region is part of what
    # comes back: a marked run is the one case where the input is also a drawing,
    # and losing it means drawing it again.
    frames(page).first.click()
    page.get_by_role("button", name="Edit this", exact=True).click()
    mark.wait_for(state="visible", timeout=10000)
    steps_default = page.input_value("#steps")
    steps_max = page.evaluate("() => document.getElementById('steps').max")
    check("the steps default differs from the top of its range", steps_max != steps_default, steps_default)
    page.fill("#prompt", "make the sky warmer")
    page.dispatch_event("#prompt", "input")
    page.fill("#seed", "1234")
    page.fill("#steps", steps_max)
    page.dispatch_event("#steps", "input")
    page.click("#count-toggle")
    page.get_by_role("menuitemradio", name="2 images").click()
    overlay = mark.bounding_box()
    page.mouse.move(overlay["x"] + 80, overlay["y"] + 90)
    page.mouse.down()
    page.mouse.move(overlay["x"] + 180, overlay["y"] + 190, steps=6)
    page.mouse.up()
    region_rows(page).nth(0).fill("change the sky to dusk")
    check(
        "the form is set up for a run",
        page.locator("#thumbs").get_by_role("img").count() == 1
        and region_rows(page).count() == 1
        and page.input_value("#count") == "2",
    )

    page.click("#go")
    check(
        "Run empties the prompt, the negative and the seed",
        page.input_value("#prompt") == "" and page.input_value("#negative") == "" and page.input_value("#seed") == "",
        repr(page.input_value("#prompt")),
    )
    check(
        "Run puts the settings back to the mode's defaults",
        page.input_value("#steps") == steps_default and page.input_value("#count") == "1",
        f"steps {page.input_value('#steps')} against {steps_default}, count {page.input_value('#count')}",
    )
    check(
        "Run takes the references and the region with it",
        page.locator("#thumbs").get_by_role("img").count() == 0
        and mark.count() == 0
        and region_rows(page).count() == 0,
    )

    # LEFT: the progress card's percentage again.
    page.wait_for_selector(".card .percent:not(:empty)", timeout=300000)
    page.click("#go")
    check(
        "Cancel reads Stopping while it stops",
        page.get_by_role("button", name=STOPPING).count() == 1,
        page.get_by_role("button", name=STOPPING).inner_text(),
    )
    wait_idle(page)
    check(
        "Cancel puts the prompt, the seed and the count back",
        page.input_value("#prompt") == "make the sky warmer"
        and page.input_value("#seed") == "1234"
        and page.input_value("#count") == "2",
        f"prompt {page.input_value('#prompt')!r}, seed {page.input_value('#seed')!r}, "
        f"count {page.input_value('#count')}",
    )
    check(
        "Cancel puts the settings and the reference back",
        page.input_value("#steps") == steps_max and page.locator("#thumbs").get_by_role("img").count() == 1,
        f"steps {page.input_value('#steps')} against {steps_max}, "
        f"thumbs {page.locator('#thumbs').get_by_role('img').count()}",
    )
    # The row is back with its instruction in it, which is the region: a row is
    # drawn for each colour a stroke was drawn in, so a row means a stroke. The
    # composed sentence is read too, because the row's text is what it is built
    # from and a row that came back empty would pass on the row alone. The area it
    # names is red: a swatch colours the next mark and the colour belongs to the
    # stroke, so the red picked earlier in this pass is still the brush in hand.
    check(
        "Cancel puts the region and its instruction back",
        mark.count() == 1
        and region_rows(page).nth(0).input_value() == "change the sky to dusk"
        and "change the sky to dusk in the red area" in page.inner_text("#region-preview"),
        page.inner_text("#region-preview")[-70:],
    )

    # Leave the form as it was found: the mode switch clears the references, and
    # the checks after this one start from an empty edit.
    page.click("label[for=mode-generate]")
    # LEFT: the theme is a data attribute on the document, not a role. The whole
    # theme block below reads it the same way, and reads the custom properties it
    # drives, which is computed style.
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
    for frame in frames(page).all():
        frame.click()
        # LEFT: the caption again.
        if page.inner_text(".prompt-line").startswith("A ceramic teapot"):
            break
    # A caption the page does not cut stays a paragraph. A role of its own is what
    # it gains when the page turns it into a control. `#stage-bar` is the id the
    # page publishes for the bar, and it is not in the design's contract.
    check(
        "a caption that fits is plain text",
        page.locator("#stage-bar").get_by_role("paragraph").count() == 1,
    )
    page.set_viewport_size({"width": 390, "height": 844})
    time.sleep(0.5)
    # LEFT: a scroll width.
    width = page.evaluate("document.documentElement.scrollWidth")
    check("phone has no sideways scroll", width <= 390, str(width))
    # LEFT: the summary line's spans and where each one sits on the line.
    rows = page.evaluate("""() => [...document.querySelectorAll('.facts span:not(.break)')]
        .map(fact => [fact.innerText, Math.round(fact.getBoundingClientRect().top)])""")
    seed = next(index for index, (text, _) in enumerate(rows) if text.startswith("Seed"))
    check(
        "a phone puts the facts on two lines: which image, then how",
        # The badge's border and padding lift its top a few pixels on the same line.
        abs(rows[0][1] - rows[seed][1]) <= 4 and rows[seed + 1][1] == rows[-1][1] > rows[seed][1] + 8,
        str(rows),
    )
    # The caption is a control here, so it names itself with the prompt it holds.
    caption = page.get_by_role("button", name=re.compile("^A ceramic teapot"))
    sheet = page.get_by_role("region", name="The whole prompt")
    check("a caption the phone cuts becomes a toggle", caption.get_attribute("aria-expanded") == "false")
    # LEFT: the print's own box.
    print_box = page.locator(".pic").bounding_box()
    caption.click()
    check(
        "a click opens the whole prompt over the print",
        caption.get_attribute("aria-expanded") == "true"
        # The sheet holds one definition per line it prints, and the prompt leads.
        and sheet.get_by_role("definition").first.inner_text().startswith("A ceramic teapot")
        and "Overcast sky" in sheet.inner_text(),
        sheet.inner_text(),
    )
    # LEFT: the print's own box again.
    check("the print does not move", page.locator(".pic").bounding_box() == print_box)
    check(
        "focus goes to Close",
        page.get_by_role("button", name="Close").evaluate("el => el === document.activeElement"),
    )
    page.keyboard.press("Escape")
    check(
        "Escape closes it and gives focus back to the label",
        sheet.count() == 0
        and caption.get_attribute("aria-expanded") == "false"
        and caption.evaluate("el => el === document.activeElement"),
    )
    caption.press("Enter")
    check("Enter opens it", sheet.count() == 1)
    page.get_by_role("button", name="Close").click()
    page.screenshot(path=OUT + "5-phone.png")
    page.evaluate("window.scrollTo(0, 560)")
    page.screenshot(path=OUT + "6-phone-form.png")
    page.set_viewport_size({"width": 1440, "height": 900})

    page.get_by_role("button", name="Clear all").click()
    check("clear empties the strip", frames(page).count() == 0)
    page.click("label[for=mode-edit]")
    check("edit empty offers a picker", button(page, "Choose an image").is_visible())
    check("no leave warning after clear", not leave_blocked(page))

    # The prompt rewriter. Both the stub and the engine report it for both modes
    # and answer with a longer prompt, so the whole path is checkable on either.
    page.reload()
    wait_idle(page)
    button = page.locator("#rewrite-toggle")
    check("the rewrite button is offered where the backend has a rewriter", button.is_visible())
    typed = "a cat"
    page.fill("#prompt", typed)
    page.dispatch_event("#prompt", "input")
    before_size = page.input_value("#size")
    rewrite = rewrite_prompt(page, button, typed)
    prompt = page.input_value("#prompt")
    check(
        "pressing it puts the rewritten prompt in the box",
        # The box holds the answer itself, and the answer is the toggle's own job:
        # a longer prompt than the one that was typed.
        prompt == rewrite["prompt"] and len(prompt) > len(typed),
        f"{len(typed)} characters typed, {len(prompt)} back",
    )
    # A shape the rewriter named is applied, so the run draws what it described.
    # A rewriter that named none leaves the menu alone, which is the page's rule.
    check(
        "a shape from the rewriter is applied to the size menu",
        page.input_value("#size") == (rewrite["size"] or before_size),
        f"the rewriter named {rewrite['size']!r}, the menu shows {page.input_value('#size')!r}",
    )

    # Your own words survive a rewrite: `typed` holds the short text you wrote,
    # while `prompt` stays the paragraph the run was actually given.
    page.fill("#prompt", typed)
    page.dispatch_event("#prompt", "input")
    rewrite = rewrite_prompt(page, button, typed)
    page.click("#go")
    wait_idle(page)
    # The card's own record of the run is what it shows. The caption under the
    # print reads back the prompt the model was given, and Reuse prompt hands
    # back the words that were typed before the rewrite replaced them.
    # LEFT: the caption has no role it keeps. It is a paragraph until it is cut
    # to two lines and a button after, so the one element that carries the whole
    # prompt is bound by its own class here, as it is above.
    on_the_card = page.locator("#stage-bar .prompt-line").inner_text()
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Reuse prompt").click()
    time.sleep(0.25)
    typed_back = page.input_value("#prompt")
    check(
        "the card keeps the words you typed, apart from the rewritten prompt",
        typed_back == typed and on_the_card == rewrite["prompt"].strip(),
        f"typed={typed_back!r} sent={on_the_card[:40]!r}",
    )

    # The check that would have caught a panel locked with `disabled`. A disabled
    # field is left out of the form the browser submits, so a locked panel once
    # sent a run with no prompt, no mode and no size.
    posted = {}
    page.on("request", lambda request: posted.update(parse_post(request)) if "/generate" in request.url else None)
    # The size is picked the way a person picks it, on the button that names its
    # megapixels. That is the setter the page runs when a size changes, and it is
    # also the stronger claim: a panel left held puts `pointer-events: none` on
    # that button, so a click that does not land is the failure this guards.
    page.locator("#tier-sizes").get_by_role("button", name="0.3 MP", exact=True).click()
    page.fill("#prompt", "a cat")
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    wait_idle(page)
    absent = [field for field in ("prompt", "mode", "size", "steps") if not posted.get(field)]
    check(
        "a run carries every field while the panel is held",
        not absent,
        "absent: " + ", ".join(absent) if absent else "prompt, mode, size and steps all present",
    )

    check("no console errors", not errors, "; ".join(errors))
    browser.close()

failed = [name for name, passed, _ in results if not passed]
print(f"\n{len(results) - len(failed)}/{len(results)} passed", "FAILED: " + ", ".join(failed) if failed else "")
sys.exit(1 if failed else 0)
