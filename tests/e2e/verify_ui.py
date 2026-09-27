"""UI check of the page's controls, against the stub. No model and no GPU.

Every binding here is a role, an accessible name, or an id the page already
publishes. None is a decorative class name, so a change to how the page is drawn
does not move the assertion. Two consequences are deliberate:

  - a Look reaches the model inside the posted prompt, so that is asserted on the
    request body, which no markup change can rename
  - the size a chip picks is asserted on the form field that is submitted, not on
    the chip's styling

The stub is enough, since this checks the page and not a model. It keeps each
backend's real form and fakes only the engine, so the controls here are the ones
the real backend declares, and a run finishes in seconds instead of minutes:

    uv run studio --stub --port <port>
    uv run --with playwright python tests/e2e/verify_ui.py <port>
    uv run --with playwright python tests/e2e/verify_ui.py <port> --headed    # watch it run
    uv run --with playwright python tests/e2e/verify_ui.py <port> --coverage  # and measure

With `--backend <id>` on the server, the page offers two backends and the picker
appears, which is what makes the backend switch reachable:

    uv run studio --stub --port <port> --backend flux2
"""

import json
import re
import shutil
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

import js_coverage
from PIL import Image
from playwright.sync_api import sync_playwright

PORT = sys.argv[1]
URL = f"http://127.0.0.1:{PORT}/"
MEASURE = "--coverage" in sys.argv
HEADED = "--headed" in sys.argv
# How the page says a run is in flight, and how it says one has finished. The run
# button is the one a user reads this from: it is Generate when idle and Cancel
# while a run goes. Reading the body's `busy` class instead would bind the suite
# to a class name, and a refactor that renamed it would break the very checks
# meant to catch that refactor.
RUNNING = re.compile("^Cancel$")
IDLE = re.compile("^Generate")
FRAME = re.compile(r"^(generate|edit), seed ")
results = []

# The page reads a reference from a file, so the upload path needs real pixels on
# disk. Two sizes, because the page reports the size it measured, and a wrong
# measurement is what the mask would take its own shape from.
SCRATCH = Path(tempfile.mkdtemp(prefix="verify-ui-"))
for name, size in (("reference-a.png", (768, 512)), ("reference-b.png", (512, 768))):
    Image.new("RGB", size, (188, 108, 52)).save(SCRATCH / name)

# Long enough that the caption under the print is cut to two lines, which is the
# state that turns the caption into the control for the whole prompt.
LONG_PROMPT = (
    "a pear on a wooden table in a sunlit kitchen with a linen cloth, a ceramic bowl "
    "and a sprig of rosemary, soft window light from the left, a shallow depth of field, "
    "warm tones, fine film grain, and the table edge running out of the frame at the "
    "bottom right corner"
)

# Two ways a browser's own store fails. Neither is a user action, so the only way
# to reach what the page does about it is to break the browser API underneath.
STORE_WILL_NOT_OPEN = """
indexedDB.open = function () {
  const request = { error: new Error('the store refused to open') };
  setTimeout(function () { if (request.onerror) request.onerror(); }, 0);
  return request;
};
"""
STORE_WILL_NOT_WRITE = """
const addOnce = IDBObjectStore.prototype.add;
IDBObjectStore.prototype.add = function (record) {
  addOnce.call(this, record);
  return addOnce.call(this, record);
};
"""


def check(name, passed, detail=""):
    results.append((name, passed))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def parse_post(request):
    """One posted form, as a plain dict of single values."""
    return {name: values[0] for name, values in urllib.parse.parse_qs(request.post_data or "").items()}


def watch_runs(page, into):
    """Keep every posted run, so an assertion can read what the engine was sent."""

    def note(request):
        if request.method == "POST" and request.url.endswith("/generate"):
            into.append(parse_post(request))

    page.on("request", note)


def watch_rewrites(page, into):
    """Keep every posted rewrite, so an assertion can read what the rewriter was sent."""

    def note(request):
        if request.method == "POST" and request.url.endswith("/rewrite"):
            into.append(parse_post(request))

    page.on("request", note)


def wait_until_running(page):
    page.get_by_role("button", name=RUNNING).wait_for(state="visible", timeout=30000)


def wait_until_idle(page):
    page.get_by_role("button", name=IDLE).wait_for(state="visible", timeout=600000)


def frames(page):
    """How many images the page says it holds.

    The strip note reads "2 images", which is a number a user reads, so this does
    not count elements named `frame`. An empty strip says "Images are kept in this
    browser" and carries no number, which is zero.
    """
    match = re.search(r"(\d+) images?", page.locator("#strip-note").inner_text())
    return int(match.group(1)) if match else 0


def frame_nodes(page):
    """The kept frames, found by the label the page gives each one."""
    return page.get_by_role("button", name=FRAME)


def set_steps(page, steps):
    """Two steps is enough for a stub run, and it is what keeps this suite quick."""
    panel = page.locator("#advanced")
    if not panel.evaluate("el => el.open"):
        page.click("#advanced summary")
    page.fill("#steps", str(steps))
    page.dispatch_event("#steps", "input")
    if panel.evaluate("el => el.open"):
        page.click("#advanced summary")


def run_once(page, prompt, steps=2):
    """One run, started and finished, in either mode.

    A run is over when the run button stops offering Cancel: the button reads
    Generate in one mode and Edit in the other, so waiting for either verb would
    bind the suite to the mode it happens to be in.
    """
    set_steps(page, steps)
    page.fill("#prompt", prompt)
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    wait_until_running(page)
    page.get_by_role("button", name=RUNNING).wait_for(state="hidden", timeout=600000)
    page.wait_for_timeout(400)


def stage_text(page):
    """What the bar under the print says about the frame it shows."""
    return page.locator("#stage-bar").inner_text().replace("\n", " ")


def stroke(page, box, start, end):
    """One stroke over the print, between two points of its own box."""
    page.mouse.move(box["x"] + start[0], box["y"] + start[1])
    page.mouse.down()
    page.mouse.move(box["x"] + end[0], box["y"] + end[1], steps=8)
    page.mouse.up()
    page.wait_for_timeout(250)


def keep_switch(page):
    """The keep item of the theme menu, opened so it is in the accessibility tree.

    A closed menu is out of that tree, so the item has to be shown before it can
    be read or clicked.
    """
    if page.locator("#theme-menu").is_hidden():
        page.click("#theme-toggle")
        page.wait_for_timeout(150)
    return page.get_by_role("menuitemcheckbox", name="Keep in this browser")


def broken_store_page(browser, fault):
    """A fresh page whose browser store is broken by `fault`."""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(fault)
    broken = context.new_page()
    broken.goto(URL)
    return context, broken


def is_new_message(page, before, text):
    """Whether the page says `text` now and did not say it before.

    A toast stays until the next run clears the strip, so a check that reads only
    the text on the page could pass on a message an earlier action left behind.
    """
    return text in page.locator("#toasts").inner_text() and text not in before


def image_transfer(page, name):
    """A drag or paste payload holding one small real image, built in the page."""
    return page.evaluate_handle(
        """async (name) => {
             const canvas = document.createElement('canvas');
             canvas.width = 96;
             canvas.height = 64;
             const blob = await new Promise(function (resolve) { canvas.toBlob(resolve, 'image/png'); });
             const transfer = new DataTransfer();
             transfer.items.add(new File([blob], name, { type: 'image/png' }));
             return transfer;
           }""",
        name,
    )


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=not HEADED)
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    # Coverage starts before the navigation, or the page's whole startup is missed.
    session = js_coverage.start(page) if MEASURE else None
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    # Clearing the gallery and turning keeping off both ask first. A user who got
    # that far has already decided, so the suite answers for them.
    page.on("dialog", lambda dialog: dialog.accept())
    posted = []
    watch_runs(page, posted)
    rewrites = []
    watch_rewrites(page, rewrites)
    page.goto(URL)

    # The header, and the mode the page opens on.
    check(
        "the header names the model and its badge",
        page.get_by_role("button", name="Qwen-Image-2.1").is_visible()
        and page.locator("[title='The weights loaded']").inner_text().strip() == "bf16",
        page.locator("[title='The weights loaded']").inner_text().strip(),
    )
    check("Generate is the mode the page opens on", page.get_by_role("radio", name="Generate").is_checked())

    # An empty prompt cannot be sent, and the button says why.
    check(
        "an empty prompt cannot be submitted",
        page.locator("#go").is_disabled() and "Write a prompt" in page.locator("#go").inner_text(),
        page.locator("#go").inner_text().replace("\n", " ")[:60],
    )
    page.fill("#prompt", "a pear on a table")
    page.dispatch_event("#prompt", "input")
    check(
        "typing enables the run button and drops the hint",
        page.locator("#go").is_enabled() and "Write a prompt" not in page.locator("#go").inner_text(),
    )

    # Edit is the mode that needs a starting image. The radio itself is hidden and
    # its label is what a user clicks, so the state is asserted on the role and the
    # click goes to the label's own association.
    page.locator("label[for=mode-edit]").click()
    check(
        "Edit asks for a starting image and a resolution",
        page.get_by_role("radio", name="Edit").is_checked()
        and page.locator("#reference").is_enabled()
        and page.locator("#edit-sizes").is_visible()
        and page.locator("#size-chips").is_hidden(),
    )
    page.locator("label[for=mode-generate]").click()
    check(
        "Generate asks for a size and not for a resolution",
        page.locator("#size-chips").is_visible() and page.locator("#edit-sizes").is_hidden(),
    )

    # A ratio chip sets the size the form actually submits.
    page.get_by_role("button", name="3:2", exact=True).click()
    submitted = page.locator("#size").input_value()
    check(
        "a ratio chip sets the size the form submits",
        submitted == "1152x768" and "768" in page.locator("#size-caption").inner_text(),
        f"{submitted} / {page.locator('#size-caption').inner_text()}",
    )

    # Under the ratio are the sizes of that shape. Picking one sets the size the
    # form submits, and the tier in force is the one marked as pressed.
    page.get_by_role("button", name="1.6 MP", exact=True).click()
    check(
        "a size tier sets the size the form submits",
        page.locator("#size").input_value() == "1536x1024"
        and page.get_by_role("button", name="1.6 MP", exact=True).get_attribute("aria-pressed") == "true",
        page.locator("#size").input_value(),
    )
    page.get_by_role("button", name="0.9 MP", exact=True).click()

    # A Look chip names itself on its row, marks itself, and reaches the model in
    # the prompt. A pick closes the row, so the mark is read by opening it again.
    page.click("details:has(summary:has-text('Look')) summary")
    camera = page.get_by_role("button", name=re.compile("^Camera"))
    camera.click()
    page.get_by_role("button", name="Close-up 85mm", exact=True).click()
    check(
        "picking a Look chip names it on its row",
        "85mm" in camera.inner_text(),
        camera.inner_text().replace("\n", " ")[:40],
    )
    camera.click()
    check(
        "the chosen Look chip is marked as pressed",
        page.get_by_role("button", name="Close-up 85mm", exact=True).get_attribute("aria-pressed") == "true",
    )
    # The pick also shows under the prompt as a chip that takes it back off.
    page.get_by_role("button", name="Remove Close-up 85mm").click()
    page.wait_for_timeout(200)
    camera.click()
    check(
        "the chip under the prompt takes the Look back off",
        page.get_by_role("button", name="Close-up 85mm", exact=True).get_attribute("aria-pressed") == "false"
        and page.locator("#look-adds").is_hidden(),
    )
    page.get_by_role("button", name="Close-up 85mm", exact=True).click()
    page.click("details:has(summary:has-text('Look')) summary")

    # The Advanced summary reads back what the panel holds. It only carries that
    # sentence while the panel is closed, so each read closes it first.
    page.click("#advanced summary")
    page.fill("#steps", "5")
    page.dispatch_event("#steps", "input")
    page.fill("#seed", "4242")
    page.dispatch_event("#seed", "input")
    page.click("#advanced summary")
    summary = page.locator("#advanced summary").inner_text()
    check(
        "the Advanced summary follows the steps and the seed",
        "5 steps" in summary and "4242" in summary,
        summary.replace("\n", " ")[:60],
    )
    page.click("#advanced summary")
    page.click("#clear-seed")
    page.click("#advanced summary")
    check("clearing the seed goes back to random", "random seed" in page.locator("#advanced summary").inner_text())

    # A run shows progress, then keeps the image and carries the Look.
    set_steps(page, 2)
    page.fill("#prompt", "a pear on a table")
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    wait_until_running(page)
    check(
        "a run in flight offers Cancel and blocks the count",
        page.get_by_role("button", name="Cancel").is_visible()
        and page.get_by_role("button", name=re.compile("change the count")).is_disabled(),
    )
    wait_until_idle(page)
    frame_nodes(page).first.wait_for(state="visible", timeout=10000)
    check(
        "a finished run keeps one image, numbered 01",
        frames(page) == 1 and frame_nodes(page).first.inner_text().strip() == "01",
    )
    check(
        "the submitted prompt carries the Look the chip picked",
        bool(posted)
        and "85mm" in posted[-1].get("prompt", "")
        and posted[-1]["prompt"].startswith("a pear on a table"),
        posted[-1].get("prompt", "")[:70] if posted else "no run was posted",
    )
    check("the form resets after a run", page.locator("#prompt").input_value() == "")

    # Cancel stops a run and keeps nothing. A 20 step stub run takes about 22s, so
    # ending well inside that is the cancel and not the run finishing on its own.
    #
    # The page ignores a click in the first half second of a run, because that is
    # the second half of a double click on Generate. No user clicks twice that
    # fast, so the wait below is the test behaving like one instead of racing it.
    before = frames(page)
    set_steps(page, 20)
    page.fill("#prompt", "a long one")
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    wait_until_running(page)
    check(
        "the run button is the one a user cancels with",
        page.get_by_role("button", name="Cancel", exact=True).is_visible(),
    )
    page.wait_for_timeout(700)
    began = time.monotonic()
    page.get_by_role("button", name="Cancel", exact=True).click()
    wait_until_idle(page)
    stopped = time.monotonic() - began
    check(
        "Cancel stops the run and keeps nothing new",
        frames(page) == before and stopped < 12,
        f"{before} frames before, {frames(page)} after, stopped in {stopped:.1f}s",
    )
    check(
        "Cancel puts back what the run emptied",
        page.locator("#prompt").input_value() == "a long one",
        page.locator("#prompt").input_value()[:40],
    )

    # The rewrite toggle replaces the prompt with a longer one.
    page.fill("#prompt", "a pear")
    page.dispatch_event("#prompt", "input")
    typed = page.locator("#prompt").input_value()
    page.click("#rewrite-toggle")
    page.wait_for_function("() => document.querySelector('#prompt').value.length > 7", timeout=120000)
    rewritten = page.locator("#prompt").input_value()
    check(
        "the rewrite toggle replaces the prompt with a longer one",
        len(rewritten) > len(typed) and rewritten != typed,
        rewritten[:70],
    )

    # A theme from the theme menu reaches the document, not only the menu.
    before_theme = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
    page.click("#theme-toggle")
    page.get_by_role("menuitemradio", name="Leica M").click()
    after_theme = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
    check(
        "picking a theme applies it to the document",
        after_theme and after_theme != before_theme,
        f"{before_theme} then {after_theme}",
    )
    check("picking a theme closes the menu", page.locator("#theme-menu").is_hidden())

    # The guide is built on its first open, so it is asked for before it is read.
    page.click("#guide-toggle")
    check(
        "the guide sheet opens with its entries",
        page.locator("#guide-sheet").is_visible() and page.locator("#guide-sheet dt").count() >= 5,
        str(page.locator("#guide-sheet dt").count()),
    )
    page.keyboard.press("Escape")
    check("Escape closes the guide sheet", page.locator("#guide-sheet").is_hidden())

    # A template fills the prompt, which is the whole reason the menu exists.
    page.fill("#prompt", "")
    page.dispatch_event("#prompt", "input")
    page.click("#templates-toggle")
    templates = page.locator("#templates button")
    check("the templates menu offers its entries", templates.count() >= 5, str(templates.count()))
    templates.first.click()
    check(
        "a template fills the prompt",
        len(page.locator("#prompt").input_value()) > 20,
        page.locator("#prompt").input_value()[:50],
    )

    # The count menu decides how many images one run makes, and a run keeps them all.
    page.click("#count-toggle")
    page.get_by_role("menuitemradio", name="2 images").click()
    check(
        "the count menu decides how many images a run makes",
        page.locator("#count").input_value() == "2",
        page.locator("#count").input_value(),
    )
    before = frames(page)
    set_steps(page, 2)
    page.fill("#prompt", "a pair of pears")
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    wait_until_idle(page)
    frame_nodes(page).nth(before + 1).wait_for(state="visible", timeout=30000)
    check("a run of two keeps two images", frames(page) == before + 2, f"{before} before, {frames(page)} after")

    # ---- A reference the user chooses ------------------------------------------
    # A reference is read from a file, and the page measures it. The size caption
    # and the mask both take their shape from that measurement, so the measured
    # size is what this reads back.
    page.locator("label[for=mode-edit]").click()
    page.set_input_files("#reference", str(SCRATCH / "reference-a.png"))
    page.get_by_role("img", name="reference-a.png").wait_for(state="visible", timeout=10000)
    chosen = page.locator("#refs-note").inner_text()
    check(
        "a chosen file becomes a reference the page names and measures",
        # The caption prints a real times sign between the two numbers.
        page.get_by_role("img", name="reference-a.png").is_visible() and "768 × 512" in chosen,  # noqa: RUF001
        chosen,
    )
    page.set_input_files("#reference", str(SCRATCH / "reference-b.png"))
    page.get_by_role("img", name="reference-b.png").wait_for(state="visible", timeout=10000)
    check(
        "a second file joins the first and is counted against the mode's limit",
        "2 of" in page.locator("#refs-note").inner_text()
        and page.get_by_role("button", name="Remove all").is_visible(),
        page.locator("#refs-note").inner_text(),
    )

    # An edit chooses its resolution, not its shape: the shape follows the image.
    # The caption reads back the pixels the choice will produce.
    page.get_by_role("button", name="1 MP", exact=True).click()
    check(
        "an edit resolution button sets the resolution the form submits",
        page.locator("#resolution").input_value() == "1024" and "1024" in page.locator("#size-caption").inner_text(),
        f"{page.locator('#resolution').input_value()} / {page.locator('#size-caption').inner_text()}",
    )
    page.get_by_role("button", name="Match", exact=True).click()
    check(
        "Match reads the size of the image the edit starts from",
        page.locator("#resolution").input_value() == "match" and "627" in page.locator("#size-caption").inner_text(),
        f"{page.locator('#resolution').input_value()} / {page.locator('#size-caption').inner_text()}",
    )

    # Each reference carries its own remove, for the one that is wrong rather than
    # all of them. Remove all shows only while there is more than one to remove.
    page.get_by_role("button", name="Remove reference-b.png").click()
    page.wait_for_timeout(250)
    check(
        "a reference can be taken off on its own",
        page.get_by_role("img", name="reference-b.png").count() == 0
        and page.get_by_role("img", name="reference-a.png").count() == 1
        and page.get_by_role("button", name="Remove all").is_hidden(),
        page.locator("#refs-note").inner_text(),
    )
    page.get_by_role("button", name="Remove reference-a.png").click()
    page.wait_for_timeout(250)
    check(
        "taking the last reference off empties the zone",
        page.get_by_role("img", name="reference-a.png").count() == 0 and page.locator("#refs-note").is_hidden(),
        f"{page.get_by_role('img', name='reference-a.png').count()} thumbnails",
    )

    # The zone itself opens the chooser, for a click and for the keyboard, and the
    # three ways an image arrives all end in the same place.
    zone = page.get_by_role("button", name="Add reference images")
    with page.expect_file_chooser() as choosing:
        zone.click()
    choosing.value.set_files(str(SCRATCH / "reference-a.png"))
    page.get_by_role("img", name="reference-a.png").wait_for(state="visible", timeout=10000)
    check(
        "the reference zone opens the file chooser for a click",
        page.get_by_role("img", name="reference-a.png").count() == 1,
        page.locator("#refs-note").inner_text(),
    )
    zone.focus()
    with page.expect_file_chooser() as choosing:
        page.keyboard.press("Enter")
    choosing.value.set_files(str(SCRATCH / "reference-b.png"))
    page.get_by_role("img", name="reference-b.png").wait_for(state="visible", timeout=10000)
    check(
        "the reference zone opens the file chooser from the keyboard",
        page.get_by_role("img", name="reference-b.png").count() == 1,
        page.locator("#refs-note").inner_text(),
    )

    # A drop and a paste are the other two ways in, and both end in the same place.
    # Playwright cannot drag a file in from the desktop, so the browser's own
    # transfer object carries one, built in the page.
    transfer = image_transfer(page, "dropped.png")
    page.dispatch_event("#refs", "dragover", {"dataTransfer": transfer})
    page.dispatch_event("#refs", "dragleave", {"dataTransfer": transfer})
    page.dispatch_event("#refs", "dragover", {"dataTransfer": transfer})
    page.dispatch_event("#refs", "drop", {"dataTransfer": transfer})
    page.get_by_role("img", name="dropped.png").wait_for(state="visible", timeout=10000)
    check(
        "an image dropped on the page becomes a reference",
        page.get_by_role("img", name="dropped.png").count() == 1,
        page.locator("#refs-note").inner_text(),
    )
    pasted = image_transfer(page, "pasted.png")
    page.evaluate(
        """(transfer) => document.dispatchEvent(new ClipboardEvent('paste',
             { clipboardData: transfer, bubbles: true, cancelable: true }))""",
        pasted,
    )
    page.get_by_role("img", name="pasted.png").wait_for(state="visible", timeout=10000)
    check(
        "an image pasted into the page becomes a reference",
        page.get_by_role("img", name="pasted.png").count() == 1,
        page.locator("#refs-note").inner_text(),
    )
    thumbs = page.get_by_role("img", name=re.compile(r"^(reference-[ab]|dropped|pasted)\.png$"))
    page.get_by_role("button", name="Remove all").click()
    page.wait_for_timeout(250)
    check(
        "Remove all drops every reference at once",
        thumbs.count() == 0 and page.locator("#refs-note").is_hidden(),
        f"{thumbs.count()} thumbnails left",
    )

    # ---- Marking a region ------------------------------------------------------
    # A stroke may only land on the picture it marks, so the brush appears only
    # while the reference is the frame on the stage. That is why this flow starts
    # from a frame the page already holds and not from an uploaded file.
    frame_nodes(page).first.click()
    page.get_by_role("button", name="Edit this").click()
    mark = page.get_by_label("Mark the area to change")
    mark.wait_for(state="visible", timeout=10000)
    brush = page.get_by_role("button", name=re.compile("^Brush width"))
    check(
        "editing a frame arms the brush on that picture",
        brush.get_attribute("aria-label") == "Brush width: medium"
        and page.get_by_role("button", name="Take back the last mark").is_disabled()
        and page.locator("#region-field").is_hidden(),
        brush.get_attribute("aria-label"),
    )

    # The magnifier is a canvas drawn over the print. It carries no accessible name
    # by design (it is hidden from assistive technology), so this counts the
    # canvases the stage shows while a stroke is drawn and once it is released.
    mark_box = mark.bounding_box()
    page.mouse.move(mark_box["x"] + 90, mark_box["y"] + 90)
    page.mouse.down()
    page.mouse.move(mark_box["x"] + 150, mark_box["y"] + 140, steps=8)
    while_drawing = page.locator("#canvas canvas:visible").count()
    page.mouse.up()
    page.wait_for_timeout(250)
    settled = page.locator("#canvas canvas:visible").count()
    check(
        "a magnifier follows the brush while a stroke is drawn",
        while_drawing == 2 and settled == 1,
        f"{while_drawing} canvases shown while drawing, {settled} after",
    )
    check(
        "a stroke opens a row in the prompt for the colour it was drawn in",
        page.get_by_label("What changes in the orange area?").is_visible()
        and page.locator("#region-preview").is_visible(),
        page.locator("#region-preview").inner_text(),
    )
    check(
        "a stroke arms both Undo and Clear",
        not page.get_by_role("button", name="Take back the last mark").is_disabled()
        and not page.get_by_role("button", name="Clear every mark").is_disabled(),
    )

    # Each colour is its own control, so each is pressed. The mark keeps the colour
    # it was drawn in, whatever is picked later.
    for colour in ("orange", "red", "green", "blue"):
        page.get_by_role("button", name=f"Mark in {colour}").click()
    check(
        "the colour pressed is the only one marked as pressed",
        page.get_by_role("button", name="Mark in blue").get_attribute("aria-pressed") == "true"
        and page.get_by_role("button", name="Mark in orange").get_attribute("aria-pressed") == "false",
    )
    stroke(page, mark_box, (240, 240), (300, 290))
    check(
        "a second colour gets its own row and its own area",
        page.get_by_label("What changes in the blue area?").is_visible()
        and page.get_by_label("What changes in the orange area?").is_visible(),
    )

    # The run waits on the rows: a marked area with no instruction is an area the
    # model would be told nothing about.
    first_blocked = page.locator("#go").inner_text().replace("\n", " ")
    page.get_by_label("What changes in the orange area?").fill("make it a stone wall")
    page.wait_for_timeout(250)
    second_blocked = page.locator("#go").inner_text().replace("\n", " ")
    check(
        "the run is blocked, and says which marked area still has no instruction",
        page.locator("#go").is_disabled() and "orange area" in first_blocked and "blue area" in second_blocked,
        f"{first_blocked} then {second_blocked}",
    )
    page.get_by_label("What changes in the blue area?").fill("make it glass")
    page.wait_for_timeout(250)
    preview = page.locator("#region-preview").inner_text()
    check(
        "the typed instructions become the sentence the page will send",
        "make it a stone wall in the orange area" in preview
        and "make it glass in the blue area" in preview
        and "<image2>" in preview
        and page.locator("#go").is_enabled(),
        preview[:110],
    )

    turned = brush.get_attribute("aria-label")
    brush.click()
    check(
        "the brush cycles to the next of its three widths",
        brush.get_attribute("aria-label") == "Brush width: broad" and turned == "Brush width: medium",
        f"{turned} then {brush.get_attribute('aria-label')}",
    )

    # A mark belongs to the picture it was drawn on. Showing another frame drops it
    # and says so, because a region carried across would repaint the wrong area.
    frame_nodes(page).nth(1).click()
    page.wait_for_timeout(300)
    dropped = page.locator("#toasts").inner_text()
    check(
        "showing another frame drops the mark and says so",
        "The mark went with its picture." in dropped and page.get_by_label("Mark the area to change").count() == 0,
        dropped.strip()[:80],
    )
    # A toast says what happened and then gets out of the way when asked.
    page.get_by_role("button", name="Dismiss").first.click()
    page.wait_for_timeout(250)
    check(
        "a toast can be dismissed",
        "The mark went with its picture." not in page.locator("#toasts").inner_text(),
        page.locator("#toasts").inner_text().strip()[:60],
    )

    # The frame the edit came from takes the brush again, and a stroke is drawn for
    # each of the two ways back out of one.
    frame_nodes(page).first.click()
    mark.wait_for(state="visible", timeout=10000)
    mark_box = mark.bounding_box()
    stroke(page, mark_box, (90, 90), (160, 150))
    page.get_by_role("button", name="Take back the last mark").click()
    page.wait_for_timeout(250)
    check(
        "Undo takes back the last mark and the row that came with it",
        page.get_by_label("What changes in the orange area?").count() == 0
        and page.locator("#region-field").is_hidden(),
    )
    stroke(page, mark_box, (120, 120), (200, 180))
    page.get_by_role("button", name="Clear every mark").click()
    page.wait_for_timeout(250)
    check(
        "Clear every mark empties the picture and the prompt with it",
        page.locator("#region-field").is_hidden() and page.locator("#region-preview").is_hidden(),
    )

    # The mask travels as one more image of the run, and the prompt has to name it,
    # so the model is told which picture carries the region. A mark lives only
    # while the picture it was drawn on is the one on the stage, so the stage stays
    # there until the run has read the mask.
    page.get_by_role("button", name="Mark in orange").click()
    stroke(page, mark_box, (90, 90), (160, 150))
    page.get_by_label("What changes in the orange area?").fill("make it a stone wall")
    set_steps(page, 4)
    page.fill("#prompt", LONG_PROMPT)
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    wait_until_running(page)
    # The frame that waits in the strip is a way back to the run in progress: the
    # print and its caption give way to the progress card. A frame of the strip is
    # what takes the print off that card, so one is shown first and the caption it
    # carries is what the way back has to clear.
    frame_nodes(page).nth(1).click()
    page.wait_for_timeout(250)
    on_a_frame = stage_text(page)
    page.get_by_role("button", name="Show the image in progress").click()
    page.wait_for_timeout(400)
    waiting_caption = stage_text(page)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(300)
    check(
        "the waiting frame in the strip shows the run in progress",
        on_a_frame != "" and waiting_caption == "" and stage_text(page) != "",
        f"caption on the frame {on_a_frame[:40]!r}, while waiting {waiting_caption!r}",
    )
    frame_nodes(page).nth(1).click()
    page.wait_for_timeout(250)
    page.get_by_role("button", name=RUNNING).wait_for(state="hidden", timeout=600000)
    page.wait_for_timeout(600)
    masked = posted[-1] if posted else {}
    carried = json.loads(masked.get("references", "[]"))
    check(
        "a marked region rides as one more image and the prompt names it",
        len(carried) == 2
        and "<image2>" in masked.get("prompt", "")
        and "make it a stone wall in the orange area" in masked.get("prompt", ""),
        f"{len(carried)} images sent, prompt {masked.get('prompt', '')[:90]}",
    )
    check(
        "a run takes the mark with it, so the next edit starts clean",
        page.locator("#region-field").is_hidden() and page.get_by_label("Mark the area to change").count() == 0,
    )

    # ---- The print, and what is over it ----------------------------------------
    # An edit keeps the picture it started from, so the print can be wiped between
    # before and after. The switch carries its own state, which is what a user reads.
    compare = page.get_by_role("button", name="Compare")
    check(
        "an edit offers the before and after wipe",
        compare.is_visible()
        and compare.get_attribute("aria-pressed") == "true"
        and page.get_by_label("Compare before and after").count() == 1,
        compare.get_attribute("aria-pressed"),
    )
    # The wipe is a control, not a picture: a user moves it with the keyboard or
    # the pointer, and the print splits where they left it. This is the one time
    # the wipe is new, so it is moved before anything draws the stage again.
    slider = page.get_by_label("Compare before and after")
    slider.press("ArrowLeft")
    stepped_split = slider.input_value()
    slider.click()
    check(
        "the wipe moves where a user puts it",
        stepped_split != "50" and slider.is_visible(),
        f"{stepped_split} after ArrowLeft, {slider.input_value()} after a click",
    )
    compare.click()
    check(
        "the compare switch takes the wipe off the print",
        page.get_by_label("Compare before and after").count() == 0
        and page.get_by_role("button", name="Compare").get_attribute("aria-pressed") == "false",
    )
    page.get_by_role("button", name="Compare").click()
    check(
        "the compare switch puts the wipe back",
        page.get_by_label("Compare before and after").count() == 1,
    )

    # Full screen is the stage at the size of the screen, and the control itself
    # says which way it goes.
    entered = False
    page.get_by_role("button", name="Full screen (F)").click()
    leave = page.get_by_role("button", name="Exit full screen (F)")
    try:
        leave.wait_for(state="visible", timeout=10000)
        entered = True
        leave.click()
        page.wait_for_function("() => !document.fullscreenElement", timeout=10000)
    except Exception:
        pass
    back = page.get_by_role("button", name="Full screen (F)")
    back.wait_for(state="visible", timeout=10000)
    check(
        "full screen takes the stage and gives it back",
        entered and back.is_visible(),
        f"entered: {entered}, back: {back.count()} controls",
    )
    # A browser may refuse full screen. The refusal has to be reported, or the
    # control looks dead. The stub always allows it, so the browser's own request
    # is made to fail underneath the page.
    before = page.locator("#toasts").inner_text()
    page.evaluate("""() => {
      window.__realFull = Element.prototype.requestFullscreen;
      Element.prototype.requestFullscreen = function () {
        return Promise.reject(new Error('the browser refused'));
      };
    }""")
    page.get_by_role("button", name="Full screen (F)").click()
    page.wait_for_timeout(1200)
    check(
        "a browser that refuses full screen is reported instead of leaving the control dead",
        is_new_message(page, before, "Full screen failed"),
        page.locator("#toasts").inner_text().replace("\n", " ")[:100],
    )
    page.evaluate("() => { Element.prototype.requestFullscreen = window.__realFull; }")
    # A browser that grants the request leaves the stage filling the screen, and
    # every check after this one would be read from there. The page goes back to
    # the size it was found at, whichever way the request went.
    if page.evaluate("() => Boolean(document.fullscreenElement)"):
        page.evaluate("() => document.exitFullscreen()")
        page.wait_for_function("() => !document.fullscreenElement", timeout=10000)

    # A cut caption is a control for the whole prompt: the caption is clamped to two
    # lines, so the rest of it opens over the print. The clamp is measured by a
    # resize watcher, so the control arrives a moment after the print does.
    caption = page.get_by_role("button", name=re.compile("rosemary"))
    caption.first.wait_for(state="visible", timeout=10000)
    check(
        "a caption cut to two lines is the control for the whole prompt",
        caption.count() == 1 and caption.get_attribute("aria-expanded") == "false",
        f"{caption.count()} prompt controls",
    )
    caption.click()
    sheet = page.get_by_role("region", name="The whole prompt")
    sheet.wait_for(state="visible", timeout=10000)
    check(
        "the sheet shows the whole of the prompt behind the caption",
        "rosemary" in sheet.inner_text() and "Prompt" in sheet.inner_text(),
        sheet.inner_text().replace("\n", " ")[:90],
    )
    page.get_by_role("button", name="Close").click()
    page.wait_for_timeout(250)
    check(
        "closing the sheet gives the caption back",
        page.get_by_role("region", name="The whole prompt").count() == 0
        and caption.get_attribute("aria-expanded") == "false",
    )
    # The caption is a control for the keyboard too, and Escape closes the sheet
    # from inside it.
    caption.press("Enter")
    sheet.wait_for(state="visible", timeout=10000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    check(
        "the caption opens the sheet from the keyboard and Escape closes it",
        page.get_by_role("region", name="The whole prompt").count() == 0
        and caption.get_attribute("aria-expanded") == "false",
    )

    # The badge on an edit names the frame it was made from, and that name is a way
    # back to it. The way back is read from what the stage says once it arrives,
    # not from a file name: one download carries the model, the mode and the seed,
    # and only Download all puts the frame number in front of a name.
    source_link = page.get_by_role("button", name=re.compile("^Show frame "))
    wanted = source_link.get_attribute("aria-label").replace("Show frame ", "")
    check("an edit names the frame it was made from", source_link.count() == 1, wanted)
    named = page.get_by_role("button", name=FRAME).filter(has_text=re.compile(rf"^{wanted}$"))
    wanted_seed = named.first.get_attribute("aria-label").split(", seed ")[1]
    source_link.click()
    page.wait_for_timeout(300)
    shown = stage_text(page)
    check(
        "the frame named on the badge is one click away",
        f"Seed {wanted_seed}" in shown and "from" not in shown,
        f"{shown[:70]} for frame {wanted} (seed {wanted_seed})",
    )

    # Reuse seed puts the image's own seed back in the form, so the same picture
    # can be asked for again with one change.
    page.get_by_role("button", name="More actions").click()
    seed_item = page.get_by_role("menuitem", name=re.compile("^Reuse seed "))
    wanted_seed = seed_item.inner_text().replace("Reuse seed ", "").strip()
    seed_item.click()
    page.wait_for_timeout(300)
    check(
        "Reuse seed puts the image's own seed back in the form",
        page.locator("#seed").input_value() == wanted_seed and page.locator("#advanced").evaluate("el => el.open"),
        f"{page.locator('#seed').input_value()} for {wanted_seed}",
    )
    page.click("#clear-seed")
    if page.locator("#advanced").evaluate("el => el.open"):
        page.click("#advanced summary")

    # The arrow keys walk the strip, which is how a keyboard user moves between
    # images. The bar under the print says which one is up.
    frame_nodes(page).nth(1).click()
    page.wait_for_timeout(250)
    second_frame = stage_text(page)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(300)
    stepped = stage_text(page)
    page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(300)
    check(
        "the arrow keys walk the strip and the stage follows",
        stepped != second_frame and stage_text(page) == second_frame,
        f"{second_frame[:40]} then {stepped[:40]}",
    )

    # ---- The strip the user keeps ----------------------------------------------
    # Every way out of the strip has to leave the page consistent: the count, the
    # stage and the browser's own store all follow the same move.
    before_remove = frames(page)
    page.get_by_role("button", name="Remove", exact=True).click()
    page.wait_for_timeout(300)
    check(
        "Remove takes the shown frame off the strip",
        frames(page) == before_remove - 1,
        f"{before_remove} before, {frames(page)} after",
    )

    downloads = []
    page.on("download", lambda download: downloads.append(download.suggested_filename))
    page.get_by_role("button", name="Download all").click()
    page.wait_for_timeout(5000)
    check(
        "Download all saves each image by frame number and one file of the prompts",
        "studio-prompts.json" in downloads and len(downloads) >= frames(page),
        str(downloads),
    )
    # The prompts file is built by the browser as the images leave. A browser that
    # will not build it has to be reported, or the run stops with no word and the
    # files already saved look like the whole of it. The stub always builds one, so
    # the browser's own object maker is made to fail underneath the page.
    before = page.locator("#toasts").inner_text()
    page.evaluate("""() => {
      window.__realUrl = URL.createObjectURL;
      URL.createObjectURL = function () { throw new Error('the browser refused the file'); };
    }""")
    page.get_by_role("button", name="Download all").click()
    page.wait_for_timeout(5000)
    check(
        "a download the browser refuses is reported instead of stopping in silence",
        is_new_message(page, before, "Download all stopped"),
        page.locator("#toasts").inner_text().replace("\n", " ")[:100],
    )
    page.evaluate("() => { URL.createObjectURL = window.__realUrl; }")

    # Reuse prompt hands back what an image was made from: the words the user typed
    # and the Look the run carried, but only for a Look this mode still offers. The
    # Look rows belong to Generate, so the mode goes back before the reuse.
    page.locator("label[for=mode-generate]").click()
    frame_nodes(page).last.click()
    page.wait_for_timeout(250)
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Reuse prompt").click()
    page.wait_for_timeout(250)
    page.click("details:has(summary:has-text('Look')) summary")
    camera = page.get_by_role("button", name=re.compile("^Camera"))
    check(
        "Reuse prompt hands back the words and the Look the image was made with",
        page.locator("#prompt").input_value() == "a pear on a table" and "85mm" in camera.inner_text(),
        f"{page.locator('#prompt').input_value()[:30]} / {camera.inner_text()}",
    )
    page.click("details:has(summary:has-text('Look')) summary")

    # The rewriter is asked about the picture an edit will change, so the image
    # travels with the question. A rewrite with no image never builds that part.
    page.locator("label[for=mode-edit]").click()
    frame_nodes(page).first.click()
    page.get_by_role("button", name="Edit this").click()
    page.wait_for_timeout(600)
    page.fill("#prompt", "a pear")
    page.dispatch_event("#prompt", "input")
    page.click("#rewrite-toggle")
    page.wait_for_function("() => document.querySelector('#prompt').value.length > 7", timeout=120000)
    asked = json.loads(rewrites[-1].get("references", "[]")) if rewrites else []
    check(
        "a rewrite of an edit carries the picture with the question",
        len(asked) == 1 and len(asked[0]) > 100,
        f"{len(asked)} images sent to the rewriter, prompt {page.locator('#prompt').input_value()[:40]}",
    )
    page.locator("label[for=mode-generate]").click()
    page.wait_for_timeout(250)

    # ---- A second tab ----------------------------------------------------------
    # Keeping is the browser's own store, and the store belongs to the address, so
    # a second tab is what proves it holds. A reload is the only other proof, and
    # a reload discards the script the coverage counters are keyed by, so the tab
    # takes both. The strip note is where a user reads which of the two is in force.
    check(
        "the theme menu carries the keep switch",
        keep_switch(page).get_attribute("aria-checked") == "true",
        keep_switch(page).get_attribute("aria-checked"),
    )
    keep_switch(page).click()
    page.wait_for_timeout(600)
    check(
        "turning keeping off leaves the images in this tab only",
        keep_switch(page).get_attribute("aria-checked") == "false"
        and "this tab" in page.locator("#strip-note").inner_text(),
        page.locator("#strip-note").inner_text(),
    )
    keep_switch(page).click()
    page.wait_for_timeout(2000)
    page.keyboard.press("Escape")
    kept = frames(page)

    tab = page.context.new_page()
    tab.on("pageerror", lambda error: errors.append("second tab: " + str(error)))
    tab.on("dialog", lambda dialog: dialog.accept())
    tab.goto(URL)
    frame_nodes(tab).first.wait_for(state="visible", timeout=30000)
    check(
        "a second tab shows the images the first one kept",
        frames(tab) == kept,
        f"{kept} kept, {frames(tab)} in the second tab",
    )

    # The strip is one strip across the tabs: a run in one reaches the other over
    # the page's own channel, which is also how a kept image arrives.
    run_once(tab, "a pear in the second tab", steps=2)
    check(
        "an image made in one tab joins the strip of the other",
        frames(page) == kept + 1 and frames(tab) == kept + 1,
        f"{kept} kept, {frames(page)} in the first tab, {frames(tab)} in the second",
    )
    # An image that arrives from the other tab is read back out of the store. An
    # image the store will not read has to be reported, or the strip stays one
    # short with nothing said about it. The stub always reads one, so the read is
    # made to fail underneath the page.
    before = page.locator("#toasts").inner_text()
    page.evaluate("""() => {
      window.__realGet = IDBObjectStore.prototype.get;
      IDBObjectStore.prototype.get = function () { throw new Error('the store refused the read'); };
    }""")
    run_once(tab, "a pear the store will not read", steps=1)
    page.wait_for_timeout(2500)
    check(
        "an image another tab cannot read back is reported instead of lost",
        is_new_message(page, before, "An image from another tab did not load"),
        page.locator("#toasts").inner_text().replace("\n", " ")[:100],
    )
    page.evaluate("() => { IDBObjectStore.prototype.get = window.__realGet; }")

    # Picking the model the page is already on is not a switch: it must not reload
    # the page or empty the strip.
    page.click("#backend-toggle")
    page.wait_for_timeout(250)
    page.get_by_role("menuitemradio", name="Qwen-Image-2.1").click()
    page.wait_for_timeout(1000)
    check(
        "picking the model the page is already on leaves the strip alone",
        page.get_by_role("button", name="Qwen-Image-2.1").is_visible() and frames(page) == kept + 1,
        f"{frames(page)} images after picking the current model",
    )

    # A frame that arrived over the channel carries no base64, so it becomes a
    # reference by reading its blob. That is the path a reloaded page takes too.
    frame_nodes(page).first.click()
    page.wait_for_timeout(250)
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Use as reference").click()
    page.get_by_role("img", name=re.compile("^Seed ")).wait_for(state="visible", timeout=10000)
    check(
        "a frame that came from the store comes back as a reference",
        page.get_by_role("img", name=re.compile("^Seed ")).count() == 1,
        page.locator("#refs-note").inner_text(),
    )
    # A picture the browser's own reader cannot read has to be reported, or the
    # reference never arrives and the empty zone says nothing about why. The stub
    # always reads one, so the reader is broken underneath the page.
    for taken in page.get_by_role("button", name=re.compile("^Remove Seed ")).all():
        taken.click()
    page.wait_for_timeout(400)
    before = page.locator("#toasts").inner_text()
    page.evaluate("""() => {
      window.__realRead = FileReader.prototype.readAsDataURL;
      FileReader.prototype.readAsDataURL = function () {
        const reader = this;
        setTimeout(function () {
          Object.defineProperty(reader, 'error', {
            value: new Error('the reader refused'), configurable: true,
          });
          if (reader.onerror) reader.onerror();
        }, 0);
      };
    }""")
    frame_nodes(page).first.click()
    page.wait_for_timeout(300)
    page.get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Use as reference").click()
    page.wait_for_timeout(1500)
    check(
        "a picture the browser cannot read is reported instead of leaving an empty zone",
        is_new_message(page, before, "did not load as a reference"),
        page.locator("#toasts").inner_text().replace("\n", " ")[:100],
    )
    page.evaluate("() => { FileReader.prototype.readAsDataURL = window.__realRead; }")

    # A switch that fails must leave the page where it was, with the picker ready
    # for another try. The stub always answers, so both failures are put in front
    # of the page here: one that never reaches the server, and one it refuses.
    page.route("**/backend", lambda route: route.abort())
    page.click("#backend-toggle")
    page.get_by_role("menuitemradio", name="FLUX.2 klein 9B").click()
    page.wait_for_timeout(2000)
    check(
        "a switch that cannot reach the server says so and leaves the page as it was",
        "The switch failed" in page.locator("#toasts").inner_text()
        and page.get_by_role("button", name="Qwen-Image-2.1").is_visible()
        and frames(page) == kept + 1,
        page.locator("#toasts").inner_text().strip()[:90],
    )
    page.unroute("**/backend")
    page.route(
        "**/backend",
        lambda route: route.fulfill(status=500, content_type="text/html", body="<p>The model did not load.</p>"),
    )
    page.click("#backend-toggle")
    page.get_by_role("menuitemradio", name="FLUX.2 klein 9B").click()
    page.wait_for_timeout(2000)
    check(
        "a switch the server refuses says why and leaves the page as it was",
        "The model did not load." in page.locator("#toasts").inner_text() and frames(page) == kept + 1,
        page.locator("#toasts").inner_text().strip()[:90],
    )
    page.unroute("**/backend")

    # A server that dies mid-run has to leave the page usable rather than counting
    # for ever, and it has to say what happened.
    page.route("**/generate", lambda route: route.abort())
    page.fill("#prompt", "a pear")
    page.dispatch_event("#prompt", "input")
    page.click("#go")
    page.wait_for_timeout(2500)
    check(
        "a run the server never answers stops and says so",
        "The server did not answer." in page.locator("#toasts").inner_text()
        and page.get_by_role("button", name=IDLE).is_visible(),
        page.locator("#toasts").inner_text().strip()[:90],
    )
    page.unroute("**/generate")

    # One tab's move reaches the other, so two tabs never disagree about the strip.
    page.get_by_role("button", name="Clear all").click()
    page.wait_for_timeout(800)
    check(
        "Clear all empties the strip and the stage with it",
        frames(page) == 0
        and page.locator("#strip-wrap").is_hidden()
        and "Nothing here yet" in page.locator("#canvas").inner_text(),
        page.locator("#strip-note").inner_text(),
    )
    check(
        "the other tab clears with it",
        frames(tab) == 0 and tab.locator("#strip-wrap").is_hidden(),
        tab.locator("#strip-note").inner_text(),
    )

    # The empty stage says what to do next, and each of the two ways it offers is a
    # control: a picture to start an edit from, or the templates to start a generate.
    page.locator("label[for=mode-generate]").click()
    page.wait_for_timeout(300)
    start = page.get_by_role("button", name="Browse templates")
    start.click()
    page.wait_for_timeout(300)
    check(
        "the empty stage offers the templates before anything is made",
        page.locator("#templates").is_visible() and page.locator("#templates button").count() >= 5,
        f"{page.locator('#templates button').count()} templates",
    )
    page.keyboard.press("Escape")
    page.locator("label[for=mode-edit]").click()
    page.wait_for_timeout(300)
    with page.expect_file_chooser() as choosing:
        page.get_by_role("button", name="Choose an image").click()
    choosing.value.set_files(str(SCRATCH / "reference-a.png"))
    page.get_by_role("img", name="reference-a.png").wait_for(state="visible", timeout=10000)
    check(
        "the empty stage offers the image an edit starts from",
        page.get_by_role("img", name="reference-a.png").count() == 1,
        page.locator("#refs-note").inner_text(),
    )
    page.get_by_role("button", name="Remove reference-a.png").click()
    page.locator("label[for=mode-generate]").click()
    page.wait_for_timeout(250)

    # ---- The other backend -----------------------------------------------------
    # The picker is there only when the page may offer more than one, and a switch
    # reloads the page with the other model's own capabilities.
    tab.click("#backend-toggle")
    tab.wait_for_timeout(250)
    check(
        "the picker offers every backend the page may use",
        tab.get_by_role("menuitemradio", name="FLUX.2 klein 9B").is_visible()
        and tab.get_by_role("menuitemradio", name="Qwen-Image-2.1").get_attribute("aria-checked") == "true",
    )
    tab.get_by_role("menuitemradio", name="FLUX.2 klein 9B").click()
    tab.get_by_role("button", name="FLUX.2 klein 9B").wait_for(state="visible", timeout=180000)
    check(
        "switching the model reloads the page as that model",
        tab.get_by_role("button", name="FLUX.2 klein 9B").is_visible(),
        tab.locator("#backend-toggle").inner_text(),
    )
    tab.click("#backend-toggle")
    tab.wait_for_timeout(250)
    tab.get_by_role("menuitemradio", name="Qwen-Image-2.1").click()
    tab.get_by_role("button", name="Qwen-Image-2.1").wait_for(state="visible", timeout=180000)
    check(
        "the picker switches back, so the server is left as it was found",
        tab.get_by_role("button", name="Qwen-Image-2.1").is_visible(),
        tab.locator("#backend-toggle").inner_text(),
    )

    # A browser store the page cannot write to has to be reported, not passed over:
    # an image that is silently not kept is lost at the next reload. The stub never
    # fails that way, so the browser's own store is broken underneath the page.
    page.route("**/rewrite", lambda route: route.abort())
    page.fill("#prompt", "a pear")
    page.dispatch_event("#prompt", "input")
    page.get_by_role("button", name="Rewrite").click()
    page.wait_for_timeout(2500)
    check(
        "a rewrite that cannot reach the server says so",
        "The rewrite failed" in page.locator("#toasts").inner_text(),
        page.locator("#toasts").inner_text().strip()[:90],
    )
    page.unroute("**/rewrite")

    page.evaluate("""() => {
      window.__addOnce = IDBObjectStore.prototype.add;
      IDBObjectStore.prototype.add = function (record) {
        window.__addOnce.call(this, record);
        return window.__addOnce.call(this, record);
      };
    }""")
    run_once(page, "a pear the store cannot write", steps=1)
    page.wait_for_timeout(1500)
    check(
        "an image the browser refuses to write is reported instead of lost",
        "did not keep image" in page.locator("#toasts").inner_text(),
        page.locator("#toasts").inner_text().strip()[:100],
    )
    page.evaluate("() => { IDBObjectStore.prototype.add = window.__addOnce; }")

    # The same for the two other requests the page makes of the store: a removal
    # and the emptying that turning keeping off does.
    page.evaluate("""() => {
      window.__realDelete = IDBObjectStore.prototype.delete;
      IDBObjectStore.prototype.delete = function () { throw new Error('the store refused the removal'); };
    }""")
    page.get_by_role("button", name="Remove", exact=True).click()
    page.wait_for_timeout(1500)
    check(
        "a removal the store refuses is reported, and the strip still drops it",
        "did not remove the image" in page.locator("#toasts").inner_text() and frames(page) == 0,
        page.locator("#toasts").inner_text().strip()[:100],
    )
    page.evaluate("() => { IDBObjectStore.prototype.delete = window.__realDelete; }")

    page.evaluate("""() => {
      window.__realClear = IDBObjectStore.prototype.clear;
      IDBObjectStore.prototype.clear = function () { throw new Error('the store refused to empty'); };
    }""")
    keep_switch(page).click()
    page.wait_for_timeout(1500)
    check(
        "a store that refuses to empty is reported when keeping goes off",
        "were not removed" in page.locator("#toasts").inner_text(),
        page.locator("#toasts").inner_text().strip()[:100],
    )
    page.evaluate("() => { IDBObjectStore.prototype.clear = window.__realClear; }")
    keep_switch(page).click()
    page.wait_for_timeout(500)
    page.keyboard.press("Escape")

    # The store is opened once and the handle kept, so a browser that refuses to
    # open one is only reachable at that first moment. The page is asked for a
    # second open with the browser's own API broken underneath it.
    page.evaluate("""() => {
      window.__realOpen = indexedDB.open.bind(indexedDB);
      indexedDB.open = function () {
        const request = { error: new Error('the store refused to open') };
        setTimeout(function () { if (request.onerror) request.onerror(); }, 0);
        return request;
      };
      store = null;
    }""")
    run_once(page, "a pear the store cannot open for", steps=1)
    page.wait_for_timeout(1500)
    check(
        "a store the browser refuses to open is reported the same way",
        "did not keep image" in page.locator("#toasts").inner_text(),
        page.locator("#toasts").inner_text().strip()[:100],
    )
    page.evaluate("() => { indexedDB.open = window.__realOpen; store = null; }")

    # ---- When the browser will not keep the images -----------------------------
    # The store is a browser API and no control makes it fail, so the suite breaks
    # the API underneath. What it checks is what the page tells the user.
    context, broken = broken_store_page(browser, STORE_WILL_NOT_OPEN)
    alerts = broken.get_by_role("alert")
    alerts.first.wait_for(state="visible", timeout=15000)
    check(
        "a store that will not open is reported as the kept images not loading",
        "did not load" in alerts.first.inner_text(),
        alerts.first.inner_text()[:90],
    )
    run_once(broken, "a pear", steps=1)
    alerts = broken.get_by_role("alert")
    alerts.first.wait_for(state="visible", timeout=60000)
    check(
        "an image the browser cannot keep is reported with what to do about it",
        "did not keep image 01" in alerts.first.inner_text() and "Download it to keep it." in alerts.first.inner_text(),
        alerts.first.inner_text()[:110],
    )
    context.close()

    context, broken = broken_store_page(browser, STORE_WILL_NOT_WRITE)
    run_once(broken, "a pear", steps=1)
    alerts = broken.get_by_role("alert")
    alerts.first.wait_for(state="visible", timeout=60000)
    check(
        "a write the store aborts is reported the same way",
        "did not keep image 01" in alerts.first.inner_text(),
        alerts.first.inner_text()[:110],
    )
    context.close()

    check("no page errors", not errors, str(errors)[:200])
    if session is not None:
        js_coverage.report(session)
    browser.close()

shutil.rmtree(SCRATCH, ignore_errors=True)

failed = [name for name, passed in results if not passed]
print(f"\n{len(results) - len(failed)}/{len(results)} passed", "FAILED: " + ", ".join(failed) if failed else "")
sys.exit(1 if failed else 0)
