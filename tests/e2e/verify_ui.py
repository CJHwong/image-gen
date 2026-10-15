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

    uv run studio --stub --backend qwen21 --port <port>
    uv run --with playwright python tests/e2e/verify_ui.py <port>
    uv run --with playwright python tests/e2e/verify_ui.py <port> --headed    # watch it run
    uv run --with playwright python tests/e2e/verify_ui.py <port> --coverage  # and measure

The suite starts on qwen21 and switches to Viggle Turbo. The official Turbo
backend remains in the picker as the configured default and third option.
"""

import contextlib
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
# button publishes that state on itself, and the button is where a user reads the
# state from: it is Generate when idle and Cancel while a run goes. Reading the
# button's name instead made these checks depend on the stylesheet, which composes
# the name by hiding all but one of the button's four labels: with no stylesheet
# the name was the whole concatenation, and the waits below timed out instead of
# failing.
RUNNING = "#go[data-state='busy']"
IDLE = "#go[data-state='idle']"
# The rewrite button's own two states, read from the label it shows. A rewrite is
# long enough to be worth stopping, so where it can be stopped is what these name.
VERB_IS_CANCEL = "() => document.getElementById('rewrite-toggle').innerText.trim() === 'Cancel'"
VERB_IS_REWRITE = "() => document.getElementById('rewrite-toggle').innerText.trim() === 'Rewrite'"
FRAME = re.compile(r"^(generate|edit), seed ")
# The base and Viggle models the suite compares. The official Turbo checkpoint is
# also in the shipping picker, but this suite measures prompt aids only on these.
# Each name is read exactly: the second carries
# the first inside it, and a substring match would find both rows.
FIRST = "Qwen-Image-2.1"
SECOND = "Qwen-Image-2.1-viggle-turbo"
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
    page.locator(RUNNING).wait_for(state="visible", timeout=30000)


def wait_until_idle(page):
    page.locator(IDLE).wait_for(state="visible", timeout=600000)


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


def edge_model(page):
    """The model the print's edge names for the frame it shows.

    The edge prints the model over the frame number, as two spans. A frame whose
    model was never recorded prints no model at all, so this reads the first span
    alone rather than the whole edge, which would carry the frame number too.
    """
    return page.locator("#canvas .shot .edge span").first.inner_text().strip()


def edge_of(name):
    """A model's name as the edge prints it: capitals, with the dashes opened out."""
    return name.upper().replace("-", " ")


def toggle_reads(name):
    """A wait condition for a switch: the title button names the model asked for.

    Read exactly, from the button's own span. A role query is a substring match,
    and the second model's name carries the first one inside it, so a role query
    would find the old title and pass before the page had reloaded at all.
    """
    return "() => document.querySelector('#backend-toggle .name').textContent === " + json.dumps(name)


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
    page.locator(RUNNING).wait_for(state="hidden", timeout=600000)
    page.wait_for_timeout(400)


def stage_text(page):
    """What the bar under the print says about the frame it shows."""
    return page.locator("#stage-bar").inner_text().replace("\n", " ")


def rewrite_verb(page):
    """The verb the rewrite button shows, as a user reads it.

    The button carries one label per stage and `hidden` picks which one, so the
    rendered text is exactly that verb. No class name is bound here, and a label
    that is hidden contributes nothing.
    """
    return page.locator("#rewrite-toggle").inner_text().strip()


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

    # The page keeps its CSS in a file of its own. No other check in this suite
    # reads a style, so this is the one that names a stylesheet which failed to
    # load. It reads the loaded sheet back and counts its rules instead of pinning
    # a value, so a restyle does not move the check.
    rules = page.evaluate(
        """() => {
             const sheet = Array.from(document.styleSheets).find(
               (one) => one.href && new URL(one.href).pathname === '/page/page.css');
             return sheet ? sheet.cssRules.length : 0;
           }"""
    )
    check(
        "the stylesheet loads from the studio and carries the page's rules",
        rules > 100,
        f"{rules} rules",
    )

    # A live region is not a role a browser computes, so both hosts carry the
    # role outright and a query reaches them by role instead of by id. The toast
    # host is always in the tree, so it is read here; the run readout is read
    # while a run shows it, in the block at the end.
    status_roles = page.get_by_role("status", include_hidden=True).evaluate_all("nodes => nodes.map((node) => node.id)")
    check(
        "the toast host is a status a role query reaches",
        "toasts" in status_roles,
        str(status_roles),
    )

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
    # The run button names the verb of the mode it is in, and one verb only. The
    # name is read here and again after the switch, because the claim is that it
    # follows the mode rather than that it is one of the two.
    verb_edit = page.get_by_role("button", name=re.compile(r"^Edit\b")).count() == 1

    # The resolution buttons drive the field the form submits, and the one in
    # force marks itself. Their names follow the chosen ratio, so the button is
    # taken by its place under its own id and not by its name.
    resolution = page.locator("#edit-sizes button").nth(1)
    wanted_resolution = resolution.get_attribute("data-value")
    resolution.click()
    check(
        "a resolution button sets the field it drives and marks itself",
        page.locator("#resolution").input_value() == wanted_resolution
        and resolution.get_attribute("aria-pressed") == "true",
        f"{page.locator('#resolution').input_value()} for {wanted_resolution}",
    )
    check(
        "the caption reads the shape an edit will take",
        page.locator("#size-caption").inner_text() == "shape follows the image",
        page.locator("#size-caption").inner_text(),
    )
    # The pick is put back, so the size the later runs submit is the one they
    # submitted before this block.
    page.locator("#edit-sizes button").nth(0).click()

    page.locator("label[for=mode-generate]").click()
    check(
        "Generate asks for a size and not for a resolution",
        page.locator("#size-chips").is_visible() and page.locator("#edit-sizes").is_hidden(),
    )
    check(
        "the run button offers the verb of the mode it is in, and one verb only",
        verb_edit and page.get_by_role("button", name=re.compile(r"^Generate\b")).count() == 1,
        f"edit {verb_edit}",
    )

    # A ratio chip sets the size the form actually submits.
    page.get_by_role("button", name="3:2", exact=True).click()
    submitted = page.locator("#size").input_value()
    check(
        "a ratio chip sets the size the form submits",
        submitted == "1152x768" and "768" in page.locator("#size-caption").inner_text(),
        f"{submitted} / {page.locator('#size-caption').inner_text()}",
    )
    # The chip in force marks itself and only it: `aria-pressed` is what a
    # reader of the DOM, and the stylesheet, has to tell the shape by.
    pressed = page.locator("#size-chips button[aria-pressed=true]")
    check(
        "a ratio chip marks itself as pressed, and only the one in force",
        page.get_by_role("button", name="3:2", exact=True).get_attribute("aria-pressed") == "true"
        and pressed.count() == 1,
        str(pressed.all_inner_texts()),
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

    # Match asks for pixels and not for a shape, so there is no shape whose sizes
    # could be offered. The pick is put back after it, so the size the later runs
    # submit is the one they submitted before this check.
    page.get_by_role("button", name="Match", exact=True).click()
    check(
        "Match hides the sizes, because the shape is not a choice then",
        page.locator("#tier-sizes").is_hidden() and page.locator("#size").input_value() == "match",
        page.locator("#size").input_value(),
    )
    page.get_by_role("button", name="3:2", exact=True).click()

    # A Look chip names itself on its row, marks itself, and reaches the model in
    # the prompt. A pick closes the row, so the mark is read by opening it again.
    page.click("details:has(summary:has-text('Look')) summary")
    camera = page.get_by_role("button", name=re.compile("^Camera"))
    shut = camera.get_attribute("aria-expanded")
    camera.click()
    open_now = camera.get_attribute("aria-expanded")
    page.get_by_role("button", name="Close-up 85mm", exact=True).click()
    check(
        "a Look row says whether it is open, and a pick closes it again",
        shut == "false" and open_now == "true" and camera.get_attribute("aria-expanded") == "false",
        f"shut {shut}, open {open_now}, after the pick {camera.get_attribute('aria-expanded')}",
    )
    check(
        "picking a Look chip names it on its row",
        "85mm" in camera.inner_text(),
        camera.inner_text().replace("\n", " ")[:40],
    )
    # The row is named for itself and then its pick. The two are one word in the
    # markup and the space between them is the cascade's: `display: flex` on the
    # toggle makes the pick a block of its own, and a text node would put a space
    # in with the stylesheet refused, where the name has always read "Lightnone".
    # The other half of this pair is checked at the end, with `page.css` refused.
    check(
        "a Look row is named for itself and its pick, with the space the cascade draws",
        page.get_by_role("button", name="Camera Close-up 85mm", exact=True).count() == 1,
        camera.aria_snapshot(),
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

    # The tail is where the whole sentence first shows, and it says what it is: the part the
    # run adds after the words in the box. Without that line a reader takes the quoted
    # sentence for the prompt itself, which is the confusion the rewrite's scope turns on.
    check(
        "the tail names itself as the sentence the run adds after your words",
        page.locator("#look-adds q").count() == 1
        and "adds this after your words" in page.locator("#look-adds .caption").inner_text().lower(),
        page.locator("#look-adds").inner_text().replace("\n", " ")[:80],
    )
    # The Rewrite button is dead while there is nothing to write out, and it says why only
    # in a tooltip, so the note that already says what a pick does also says what the
    # rewriter touches: the words you typed and the words in the marked areas, with the
    # Look added after them. Read through the section's own id, since the note carries none.
    check(
        "the Look note says the rewriter writes your words and leaves the Look to the run",
        "writes out the words you typed, and the words in the marked areas" in page.locator("#look").inner_text(),
        page.locator("#look").inner_text().replace("\n", " ")[-90:],
    )

    # A pick from a row's own chips puts a chip under the prompt and takes the
    # row's chips away, so the content above the row changes height and the row
    # would slide out from under the pointer. The sidebar scrolls by as much.
    # The chip is scrolled into view first, so the click below cannot scroll the
    # sidebar itself and leave this measuring its own setup.
    light = page.get_by_role("button", name=re.compile("^Light"))
    light.click()
    overcast = page.get_by_role("button", name="Overcast", exact=True)
    overcast.scroll_into_view_if_needed()
    before = light.bounding_box()["y"]
    overcast.click()
    after = light.bounding_box()["y"]
    check(
        "a pick leaves its row where the pointer left it",
        abs(after - before) <= 2,
        f"the row moved {round(after - before, 1)} px",
    )
    page.get_by_role("button", name="Remove Overcast").click()
    page.wait_for_timeout(200)

    # Only the Realism row carries an avoid part, and it is shown wherever the
    # mode declares a negative prompt, because it is what the model will be told
    # not to draw.
    page.get_by_role("button", name=re.compile("^Realism")).click()
    page.get_by_role("button", name="Real person", exact=True).click()
    note = page.locator("#look-adds .look-avoids")
    # Read without waiting: an absent note is a failed check and not a timeout,
    # so the suite goes on to the checks after it.
    said = note.inner_text() if note.count() else ""
    check(
        "a Look whose avoid part rides the negative says what it will carry",
        "beauty filter" in said and "twice as long" in said,
        said[:70],
    )
    page.get_by_role("button", name="Remove Real person").click()
    page.wait_for_timeout(200)
    page.click("details:has(summary:has-text('Look')) summary")

    # The Advanced summary reads back what the panel holds. It only carries that
    # sentence while the panel is closed, so each read closes it first.
    page.click("#advanced summary")
    clear_absent = page.locator("#clear-seed").is_hidden()
    page.fill("#steps", "5")
    page.dispatch_event("#steps", "input")
    check(
        "each slider's readout follows its own input",
        page.locator("#steps-value").inner_text() == page.locator("#steps").input_value()
        and page.locator("#guidance-value").inner_text() == page.locator("#guidance").input_value()
        and page.locator("#cfg-value").inner_text() == page.locator("#cfg").input_value(),
        f"{page.locator('#steps-value').inner_text()} / {page.locator('#guidance-value').inner_text()}"
        f" / {page.locator('#cfg-value').inner_text()}",
    )
    page.fill("#seed", "4242")
    page.dispatch_event("#seed", "input")
    clear_present = page.locator("#clear-seed").is_visible()
    page.click("#advanced summary")
    summary = page.locator("#advanced summary").inner_text()
    check(
        "the Advanced summary follows the steps and the seed",
        "5 steps" in summary and "4242" in summary,
        summary.replace("\n", " ")[:60],
    )
    page.click("#advanced summary")
    page.click("#clear-seed")
    check(
        "Clear shows exactly while there is a seed, and takes it away with it",
        clear_absent
        and clear_present
        and page.locator("#seed").input_value() == ""
        and page.locator("#clear-seed").is_hidden(),
        f"absent {clear_absent}, present {clear_present}, seed {page.locator('#seed').input_value()!r}",
    )
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
        page.locator(RUNNING).is_visible()
        and page.get_by_role("button", name=re.compile("change the count")).is_disabled(),
    )
    # A rewrite writes into the form a run is using, and the rewriter does not fit beside an
    # engine, so the press waits for the run. Nothing asked for here: the state is read.
    check(
        "the press waits for a run, with no words put in the box",
        page.locator("#rewrite-toggle").is_disabled() and not page.locator("#prompt").input_value().strip(),
        f"disabled {page.locator('#rewrite-toggle').is_disabled()}, box {page.locator('#prompt').input_value()[:20]!r}",
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
        page.locator(RUNNING).is_visible(),
    )
    # One verb and nothing else, with the stylesheet loaded. The page hides the
    # labels it is not using, so two of them showing at once means a rule has
    # taken the choice back from the DOM, which is what a failed stylesheet used
    # to look like. The same claim is made with the stylesheet refused at the end.
    check(
        "the run button is called Cancel and nothing else",
        page.get_by_role("button", name="Cancel", exact=True).count() == 1,
        page.locator("#go").aria_snapshot(),
    )
    # The progress card is the page's own drawing of a run, and the module that
    # draws it is new: its plate, its exposure and its percentage are what the
    # real-run check reads, so the stub reads them here too. The exposure is the
    # same reading as the percentage, held on the plate where the cascade picks
    # it up, so the two are asserted against each other and not against a
    # number. A step has to have landed for the percentage to read anything.
    page.wait_for_function(
        "() => { const p = document.querySelector('.card .percent');"
        " return Boolean(p && p.textContent && p.textContent !== '0%'); }",
        timeout=30000,
    )
    card = page.evaluate(
        """() => ({
             percent: document.querySelector('.card .percent').textContent,
             exposed: getComputedStyle(document.querySelector('.card .exposure'))
               .getPropertyValue('--exposed').trim(),
           })"""
    )
    check(
        "the progress card paints the exposure the percentage reads",
        page.locator(".card .plate").count() == 1
        and page.locator(".card .percent").count() == 1
        and page.locator(".card .edge").inner_text().strip() != ""
        and card["exposed"] == card["percent"],
        f"{card['percent']} shown, --exposed {card['exposed']}",
    )
    page.wait_for_timeout(700)
    began = time.monotonic()
    page.locator(RUNNING).click()
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

    # A rewrite is worth stopping, so the button offers it: locked while the
    # rewriter gets ready, which is when a cold one loads about 19 GB, and Cancel
    # once it writes. The stub spends 1.2s preparing and 3s writing in slices, so
    # both phases last long enough to read here.
    page.fill("#prompt", "a pear")
    page.dispatch_event("#prompt", "input")
    typed = page.locator("#prompt").input_value()
    page.click("#rewrite-toggle")
    page.wait_for_timeout(300)
    check(
        "the rewrite button is locked while the rewriter gets ready",
        rewrite_verb(page) == "Rewrite" and page.locator("#rewrite-toggle").is_disabled(),
        f"{rewrite_verb(page)!r}, disabled {page.locator('#rewrite-toggle').is_disabled()}",
    )
    page.wait_for_function(VERB_IS_CANCEL, timeout=30000)
    check(
        "the rewrite button becomes Cancel once the model writes",
        page.locator("#rewrite-toggle").is_enabled(),
        rewrite_verb(page),
    )
    page.click("#rewrite-toggle")
    check(
        "cancelling a rewrite says it is stopping",
        rewrite_verb(page).startswith("Stopping"),
        rewrite_verb(page),
    )
    page.wait_for_function(VERB_IS_REWRITE, timeout=30000)
    page.wait_for_timeout(400)
    check(
        "a cancelled rewrite leaves the prompt as it was and says nothing alarming",
        page.locator("#prompt").input_value() == typed
        and "The rewrite failed" not in page.locator("#toasts").inner_text(),
        f"{page.locator('#prompt').input_value()[:30]!r}, toast {page.locator('#toasts').inner_text().strip()[:50]!r}",
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

    # The menu reads the theme back out of the store, so the pick is marked where
    # a user sees it. The closed menu leaves the accessibility tree, so it is
    # opened again before the marks are read.
    page.click("#theme-toggle")
    page.wait_for_timeout(150)
    check(
        "the theme menu marks the theme in force",
        page.get_by_role("menuitemradio", name="Leica M").get_attribute("aria-checked") == "true"
        and page.get_by_role("menuitemradio", name="Darkroom").get_attribute("aria-checked") == "false",
        page.get_by_role("menuitemradio", name="Leica M").get_attribute("aria-checked"),
    )
    page.keyboard.press("Escape")

    # The pick is kept in this browser, and the inline head script applies it
    # before the menu exists. The check above cannot see that: it reads the
    # document the pick itself painted. A fresh page in this context can.
    fresh = page.context.new_page()
    fresh.on("pageerror", lambda error: errors.append("theme page: " + str(error)))
    fresh.goto(URL)
    check(
        "a fresh page opens on the saved theme",
        fresh.evaluate("() => document.documentElement.getAttribute('data-theme')") == "leica",
        str(fresh.evaluate("() => document.documentElement.getAttribute('data-theme')")),
    )
    fresh.close()

    # ---- The four menus, and how each one closes -------------------------------
    # One manager owns the four menus, so they share one way in and the same ways
    # out. A pick closes the menu, and a check above reads one from two of them.
    # These read the other ways out, on the count menu: it is the shortest, and it
    # keeps the run the rest of the suite does out of the picture.
    page.click("#count-toggle")
    page.wait_for_timeout(200)
    opened = page.locator("#count-toggle").get_attribute("aria-expanded")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check(
        "Escape closes a menu, clears its toggle's aria-expanded and puts focus back",
        opened == "true"
        and page.locator("#count-menu").is_hidden()
        and page.locator("#count-toggle").get_attribute("aria-expanded") == "false"
        and page.evaluate("() => document.activeElement.id") == "count-toggle",
        f"expanded {opened}, then focus {page.evaluate('() => document.activeElement.id')}",
    )

    page.click("#count-toggle")
    page.wait_for_timeout(200)
    page.locator("body").click(position={"x": 5, "y": 5})
    page.wait_for_timeout(200)
    check(
        "a click outside closes the open menu",
        page.locator("#count-menu").is_hidden()
        and page.locator("#count-toggle").get_attribute("aria-expanded") == "false",
        page.locator("#count-toggle").get_attribute("aria-expanded"),
    )

    page.click("#count-toggle")
    page.wait_for_timeout(200)
    page.click("#theme-toggle")
    page.wait_for_timeout(200)
    check(
        "opening one menu closes the one already open",
        page.locator("#count-menu").is_hidden() and page.locator("#theme-menu").is_visible(),
        f"count hidden {page.locator('#count-menu').is_hidden()}, "
        f"theme visible {page.locator('#theme-menu').is_visible()}",
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    page.click("#count-toggle")
    page.wait_for_timeout(200)
    first_item = page.evaluate("() => document.activeElement.textContent.trim()")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(200)
    walked_to = page.evaluate("() => document.activeElement.textContent.trim()")
    check(
        "the arrow keys walk a menu's items",
        walked_to != first_item and walked_to.endswith("images"),
        f"{first_item} then {walked_to}",
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # The store's one rule is invisible in the page while the theme is its only
    # consumer: a redraw scoped to the theme draws the same DOM a global redraw
    # would. So the rule is checked on the store itself, through the module the
    # page already loaded. `progress` and `view` are fields no consumer names.
    store_rules = page.evaluate("""async () => {
      const store = await import('/page/lib/state.js');
      const byField = [];
      const byGroup = [];
      store.subscribe(['progress'], (field) => byField.push(field));
      store.subscribe(['results'], (field) => byGroup.push(field));
      store.set('view', 'a');
      const other = byField.length;
      const otherGroup = byGroup.length;
      store.set('progress', 'b');
      const named = byField.length;
      const namedGroup = byGroup.length;
      store.set('progress', 'b');
      const same = byField.length;
      store.set('progress', 'c');
      const changed = byField.length;
      return { other, otherGroup, named, namedGroup, same, changed };
    }""")
    check(
        "the store redraws only the consumers that named the changed field",
        store_rules == {"other": 0, "otherGroup": 1, "named": 1, "namedGroup": 2, "same": 1, "changed": 2},
        str(store_rules),
    )

    # The guide is built on its first open, so it is asked for before it is read.
    page.click("#guide-toggle")
    check(
        "the guide sheet opens with its entries",
        page.locator("#guide-sheet").is_visible() and page.locator("#guide-sheet dt").count() >= 5,
        str(page.locator("#guide-sheet dt").count()),
    )
    # The Look and the Rewrite are the page's two prompt aids, and the manual named neither
    # of them. The Look entry says the run adds its sentence after your words. The Rewrite
    # entry says what it leaves alone, which is the scope a user cannot read off the page.
    entries = page.locator("#guide-sheet dt").all_inner_texts()
    check(
        "the guide names the Look and the Rewrite, and says what each one leaves alone",
        "A Look" in entries and "Rewrite" in entries,
        ", ".join(entries),
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
    # The empty zone and the tile that offers one more are drawn by the reference
    # tree, and nothing else here reads them: the checks below bind to the
    # thumbnails, the note and the remove, so a tree that lost its empty state
    # would still pass. The checks in this block read that part of it.
    empty = page.locator("#refs-empty")
    check(
        "the empty zone names what the mode wants",
        empty.is_visible()
        and page.locator("#refs-title").inner_text() == "Start from an image"
        and page.locator("#refs-sub").inner_text() == "Optional. Drop, paste or choose one.",
        page.locator("#refs-title").inner_text(),
    )

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
    check(
        "an empty zone stands down, and the edit words name what to add",
        empty.is_hidden()
        and page.locator("#refs-title").inner_text() == "Add the image to edit"
        and page.locator("#refs-sub").inner_text().startswith("Drop, paste or choose up to "),
        f"{page.locator('#refs-title').inner_text()} / {page.locator('#refs-sub').inner_text()}",
    )
    # The thumbnail carries the name of the image it holds, which is how a
    # sighted user tells two references apart, and the tile offers one more while
    # the mode takes one.
    check(
        "a thumbnail carries its own name, and a tile offers one more",
        page.locator("#thumbs .thumb").first.get_attribute("title") == "reference-a.png"
        and page.locator("#thumbs .add-tile").count() == 1,
        str(page.locator("#thumbs .thumb").first.get_attribute("title")),
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
    # Empty again in edit mode: the zone comes back with the edit words, and no
    # tile offers one more, because there is nothing to add to.
    check(
        "emptying the list brings the empty zone back",
        page.locator("#refs-empty").is_visible()
        and page.locator("#refs-title").inner_text() == "Add the image to edit"
        and page.locator("#thumbs .add-tile").count() == 0,
        page.locator("#refs-title").inner_text(),
    )
    # Off the edit mode the tile is gone even with an image in the list: a
    # generate starts from one image, so there is no room to offer, and the note
    # says the image is there to be replaced rather than counted against a limit.
    # A page of its own, so the mode switch does not empty the form the checks
    # below set up.
    other_context = browser.new_context(viewport={"width": 1440, "height": 900})
    other = other_context.new_page()
    other.goto(URL)
    other.set_input_files("#reference", str(SCRATCH / "reference-a.png"))
    other.get_by_role("img", name="reference-a.png").wait_for(state="visible", timeout=10000)
    check(
        "a generate holds one image and offers no tile",
        other.locator("#thumbs .add-tile").count() == 0
        and other.locator("#refs-note").inner_text() == "Drop or paste another image to replace it.",
        other.locator("#refs-note").inner_text(),
    )
    other_context.close()

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
    # A template that names the region is offered only where the brush is in hand,
    # and until one is drawn the run says what it waits for. The prompt is cleared
    # again, so the rows below are the only instruction the later checks see.
    page.click("#templates-toggle")
    page.get_by_role("menuitem", name="Mark a region").click()
    check(
        "a template that names the region waits for a drawn one",
        page.locator("#go-sub").inner_text() == "Draw the region this prompt names",
        page.locator("#go-sub").inner_text(),
    )
    page.fill("#prompt", "")
    page.dispatch_event("#prompt", "input")
    page.wait_for_timeout(200)

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
    # The row is drawn tall enough for the line it holds, before anything is typed in it. A
    # textarea measures itself off its own content and has none while it is still detached, so
    # one grown before it is in the page takes the height of nothing: the row used to be drawn
    # as a squashed line and only opened up when someone typed in it. `offsetHeight` is the
    # box with its border, which is what `scrollHeight` is measured against.
    drawn = page.get_by_label("What changes in the orange area?").evaluate(
        "node => [node.offsetHeight, node.scrollHeight]"
    )
    check(
        "a row is drawn as tall as its own line, before anything is typed",
        abs(drawn[0] - drawn[1]) <= 2,
        f"drawn {drawn[0]}px against its line at {drawn[1]}px",
    )
    # The note beside the rows is where a user decides what the mark is for, so it carries
    # both halves: the whole area is repainted, and the change can still reach past it. The
    # second half is the measured one: at 22 percent coverage, 21.4 percent of the change
    # landed past the object.
    # A mark is one more image of one run, so there is no batch to make while one is drawn.
    check(
        "a drawn region puts the batch choice out of force",
        page.locator("#each-choice").is_hidden() and page.locator("#each-note").is_hidden(),
        f"choice hidden {page.locator('#each-choice').is_hidden()}, note hidden {page.locator('#each-note').is_hidden()}",
    )
    check(
        "the note by the rows says what the mark does, and what it does not",
        "whole marked area is repainted" in page.inner_text("#region-note")
        and "reach past it" in page.inner_text("#region-note"),
        page.inner_text("#region-note"),
    )
    # A rewrite of a row answers with a paragraph, not a phrase, so the field has to hold one:
    # on one line the words the model is about to read are the words the user cannot see.
    row_field = page.get_by_label("What changes in the orange area?")
    row_field.fill("make it a stone wall")
    page.wait_for_timeout(200)
    short = row_field.evaluate("node => node.clientHeight")
    row_field.fill(
        "Replace the entire blurred background behind the pear with a natural stone wall of "
        "irregular gray and beige stones, fitted together with visible mortar seams, softly "
        "out of focus to match the depth of field, and keep the pear, the linen cloth, the "
        "table and the warm light exactly as they are."
    )
    page.wait_for_timeout(200)
    long = row_field.evaluate("node => node.clientHeight")
    check(
        "a row grows to hold the paragraph a rewrite puts in it",
        long > short and row_field.evaluate("node => node.tagName") == "TEXTAREA",
        f"one line {short}px, a paragraph {long}px, field {row_field.evaluate('node => node.tagName')}",
    )
    # The rows go back as they were found, empty, because the checks after this one read which
    # area is still waiting for an instruction.
    row_field.fill("")
    page.wait_for_timeout(200)
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
    # A pick is an instruction by itself, and a Retouch pick names the area it wants: with no
    # mark drawn there is nothing to name, and the page says so rather than sending the token
    # to the model as it stands. The section is opened only to reach the chips and is left as
    # it was found, because a later check toggles it.
    look_open = page.locator("details#look").evaluate("node => node.open")
    if not look_open:
        page.click("details#look summary")
    page.get_by_role("button", name=re.compile("^Retouch")).click()
    page.get_by_role("button", name="Smooth the skin", exact=True).click()
    page.wait_for_timeout(250)
    check(
        "a pick that wants a marked area waits for a drawn one",
        page.locator("#go").is_disabled() and "Draw the region this prompt names" in page.locator("#go").inner_text(),
        page.locator("#go").inner_text().replace("\n", " "),
    )
    stroke(page, mark_box, (90, 90), (160, 150))
    # The pick's sentence carries the mark's token, and the page puts the masked image's number
    # where it stands. Nothing is typed and the row is empty, so the sentence is the pick and
    # the pin: this is the sentence the option was measured with, to the character.
    pick_sentence = (
        "Smooth the skin on the face, keeping the pores and the natural texture visible in the area marked in <image2>."
    )
    composed = page.locator("#region-preview").inner_text()
    check(
        "a Retouch pick alone is the sentence the marked run sends",
        composed == pick_sentence + " Keep the background and everything else unchanged."
        and page.locator("#go").is_enabled(),
        composed,
    )
    # A prompt that names the mark itself keeps its own reference, and the pick's sentence rides
    # with it: the lead is the words the run sends, so reading the prompt field alone would drop
    # the pick here.
    page.fill("#prompt", "Change only the wall in the area marked in [the region you marked].")
    page.dispatch_event("#prompt", "input")
    page.wait_for_timeout(250)
    both = page.locator("#region-preview").inner_text()
    check(
        "a prompt that names the mark and a pick both reach the sentence",
        "Change only the wall in the area marked in <image2>." in both and pick_sentence in both,
        both[:160],
    )
    if not look_open:
        page.click("details#look summary")
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
    page.locator(RUNNING).wait_for(state="hidden", timeout=600000)
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
    # The pick rode along, and its sentence carries the mark's own reference, so the model is
    # told which picture holds the area it changes.
    check(
        "the marked run carries the pick, with the mark named in it",
        pick_sentence in masked.get("prompt", "")
        and masked.get("prompt", "").endswith("Keep the background and everything else unchanged."),
        masked.get("prompt", "")[-150:],
    )
    # The card draws a frame's caption as the sentence the run sent, with the pick as
    # its muted end. A marked run pins the rest of the picture after that sentence, so
    # the pick stands inside it and not at its end: the card cut the last sentence off
    # by the pick's length, which cut the pin and left the pick half-written above
    # itself. The caption is a control only where it is cut short, and LONG_PROMPT is.
    captions = page.get_by_role("button", name=re.compile("Keep the background and everything else unchanged."))
    shown = captions.first.inner_text() if captions.count() else ""
    check(
        "the caption of a marked run keeps its sentence whole, with the pick in it once",
        shown.count("Smooth the skin") == 1
        and shown.endswith("Keep the background and everything else unchanged.")
        and "make it a stone wall in the orange area" in shown,
        shown[-110:],
    )
    # The pick was this check's, so it comes off again and the sections below read the form
    # as they found it. A run may have put the form back already, so this asks first.
    remove = page.get_by_role("button", name="Remove Smooth the skin")
    if remove.count():
        remove.click()
        page.wait_for_timeout(250)
    check(
        "a run takes the mark with it, so the next edit starts clean",
        page.locator("#region-field").is_hidden() and page.get_by_label("Mark the area to change").count() == 0,
    )

    # The six rows the edit form offers, read as the generate ones were read above: they are
    # the finishing rows, and no row of the generate set is among them. The text is read
    # from the DOM, because the section may be closed here and a closed row renders nothing.
    edit_rows = [name.text_content() for name in page.locator("#look-rows .look-row .label").all()]
    check(
        "the edit form offers the six finishing rows",
        edit_rows == ["Exposure", "White balance", "Grade", "Lens", "Finish", "Retouch"],
        ", ".join(edit_rows),
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

    # The bar takes its height from the caption, and the stage takes its height
    # from the bar, so a caption that grew and shrank with the prompt moved every
    # control in the row and resized the picture as the user walked the strip.
    # Two lines are reserved now, filled or not. The caption is read with each
    # shape written into it, which is the one way to hold the frame still while
    # the prompt changes length; the claim is on the bar and the stage.
    shapes = caption.first.evaluate("""(node) => {
      const box = (el) => { const b = el.getBoundingClientRect();
        return [Math.round(b.y), Math.round(b.height)]; };
      const bar = document.getElementById('stage-bar');
      const canvas = document.getElementById('canvas');
      const read = () => ({bar: box(bar), stage: box(canvas), caption: box(node)});
      const written = node.textContent;
      node.textContent = 'a pear';
      const short = read();
      node.textContent = written;
      return {short: short, long: read()};
    }""")
    check(
        "the stage does not move when the caption changes length",
        shapes["short"] == shapes["long"],
        f"one line {shapes['short']}, two lines {shapes['long']}",
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
    # A step corrects the strip's own scroll and focus across the redraw, and
    # the redraw lands after the key returns. The correction is the strip's, so
    # the frame it shows is the one focus ends on.
    frame_nodes(page).nth(0).click()
    page.wait_for_timeout(250)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(300)
    shown = page.locator("#strip .frame.selected").get_attribute("aria-label")
    focused = page.evaluate("document.activeElement.getAttribute('aria-label')")
    check(
        "an arrow key leaves focus on the frame it shows",
        focused == shown,
        f"{shown} shown, focus on {focused}",
    )

    # ---- The strip the user keeps ----------------------------------------------
    # Every way out of the strip has to leave the page consistent: the count, the
    # stage and the browser's own store all follow the same move.
    before_remove = frames(page)
    # The frames after the one that goes are moved along and not rebuilt. A
    # rebuilt frame reloads its image, so the image the browser held is the
    # claim, and it is why the strip keys each frame by its own image.
    kept_thumb = frame_nodes(page).last.locator("img").element_handle()
    kept_src = page.evaluate("(img) => img.src", kept_thumb)
    page.evaluate(
        """(img) => {
      window.__reloaded = 0;
      img.addEventListener('load', () => { window.__reloaded++; });
    }""",
        kept_thumb,
    )
    page.get_by_role("button", name="Remove", exact=True).click()
    page.wait_for_timeout(400)
    check(
        "Remove takes the shown frame off the strip",
        frames(page) == before_remove - 1,
        f"{before_remove} before, {frames(page)} after",
    )
    check(
        "a frame the strip moves along keeps its own image",
        page.evaluate("(img) => img.isConnected", kept_thumb)
        and page.evaluate("(img) => img.src", kept_thumb) == kept_src
        and page.evaluate("window.__reloaded") == 0,
        f"connected {page.evaluate('(img) => img.isConnected', kept_thumb)}, "
        f"reloads {page.evaluate('window.__reloaded')}",
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

    # A tab that opens on kept images is the first entry: the store reads them
    # back, un-hides the strip and draws the print in one task, and the strip's
    # frames arrive from a Lit render a microtask later. The stage the print was
    # fitted to is not the stage it lands in, and nothing re-fit it, so the first
    # entry kept a print too big for it until the next resize. The claim is that
    # the size a settled page gives the print is the size fitStage gives it: the
    # same page re-fits it on a resize, and the two have to agree.
    def printed(pane):
        # The print is the first image in the frame; a frame shown against its
        # source carries a second one over it.
        box = pane.locator("#canvas .pic img").first.bounding_box()
        return (round(box["width"]), round(box["height"]))

    tab.wait_for_timeout(200)
    on_entry = printed(tab)
    tab.evaluate("() => window.dispatchEvent(new Event('resize'))")
    tab.wait_for_timeout(200)
    refitted = printed(tab)
    check(
        "the first entry fits the print to the stage it lands in",
        on_entry == refitted and on_entry[0] > 100,
        f"{on_entry[0]}x{on_entry[1]} on entry, {refitted[0]}x{refitted[1]} after a re-fit",
    )

    # The strip is one strip across the tabs: a run in one reaches the other over
    # the page's own channel, which is also how a kept image arrives.
    run_once(tab, "a pear in the second tab", steps=2)
    check(
        "an image made in one tab joins the strip of the other",
        frames(page) == kept + 1 and frames(tab) == kept + 1,
        f"{kept} kept, {frames(page)} in the first tab, {frames(tab)} in the second",
    )

    # The channel runs both ways, and every check above had this tab as the one
    # that acts. This is the other direction: the setting is changed in the
    # other tab, and this one has to move with it. The strip note is where a
    # user reads which of the two is in force, so it is where the move is read.
    # It goes back on, because the images this tab keeps are what the checks
    # below read.
    keep_switch(tab).click()
    page.wait_for_timeout(800)
    check(
        "turning keeping off in the other tab reaches this one",
        "this tab" in page.locator("#strip-note").inner_text()
        and keep_switch(page).get_attribute("aria-checked") == "false",
        page.locator("#strip-note").inner_text(),
    )
    keep_switch(tab).click()
    page.wait_for_timeout(1500)
    check(
        "turning it back on in the other tab reaches this one too",
        "this tab" not in page.locator("#strip-note").inner_text()
        and keep_switch(page).get_attribute("aria-checked") == "true",
        page.locator("#strip-note").inner_text(),
    )
    page.keyboard.press("Escape")

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
    page.get_by_role("menuitemradio", name=FIRST, exact=True).click()
    page.wait_for_timeout(1000)
    check(
        "picking the model the page is already on leaves the strip alone",
        page.get_by_role("button", name=FIRST).is_visible() and frames(page) == kept + 1,
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
    page.get_by_role("menuitemradio", name=SECOND, exact=True).click()
    page.wait_for_timeout(2000)
    check(
        "a switch that cannot reach the server says so and leaves the page as it was",
        "The switch failed" in page.locator("#toasts").inner_text()
        and page.get_by_role("button", name=FIRST).is_visible()
        and frames(page) == kept + 1,
        page.locator("#toasts").inner_text().strip()[:90],
    )
    page.unroute("**/backend")
    page.route(
        "**/backend",
        lambda route: route.fulfill(status=500, content_type="text/html", body="<p>The model did not load.</p>"),
    )
    page.click("#backend-toggle")
    page.get_by_role("menuitemradio", name=SECOND, exact=True).click()
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
        "The server did not answer." in page.locator("#toasts").inner_text() and page.locator(IDLE).is_visible(),
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
        tab.get_by_role("menuitemradio", name=SECOND, exact=True).is_visible()
        and tab.get_by_role("menuitemradio", name=FIRST, exact=True).get_attribute("aria-checked") == "true",
    )
    # LEFT: the second line of a row has no role of its own and is hidden from
    # assistive technology on purpose, so it is read as text of the row it is in.
    check(
        "each model says what it is before you switch to it",
        "Full quality" in tab.get_by_role("menuitemradio", name=FIRST, exact=True).inner_text()
        and "six steps" in tab.get_by_role("menuitemradio", name=SECOND, exact=True).inner_text(),
        tab.get_by_role("menuitemradio", name=SECOND, exact=True).inner_text(),
    )
    tab.get_by_role("menuitemradio", name=SECOND, exact=True).click()
    tab.wait_for_function(toggle_reads(SECOND), timeout=180000)
    check(
        "switching the model reloads the page as that model",
        tab.get_by_role("button", name=SECOND).is_visible(),
        tab.locator("#backend-toggle").inner_text(),
    )
    # The aids this model offers are the ones its own six-step sample kept. One row is
    # open at a time, so each is read on its own. The Medium row carries all six the
    # sample ran, and the Camera row carries five of its six: Deep focus is the one
    # that did not visibly work. That name is in the regex, so its absence is a check
    # that fails rather than one that silently passes. The rows sit behind a summary,
    # and a closed details is out of the accessibility tree, so the sheet is opened
    # the way a reader opens it.
    tab.click("#look summary")
    tab.wait_for_timeout(300)
    tab.locator("#look-rows").get_by_role("button", name=re.compile("^Medium")).click()
    tab.wait_for_timeout(250)
    medium = tab.locator("#look-rows").get_by_role(
        "button", name=re.compile("^(Documentary|Phone snapshot|Watercolor|Ink drawing|3D render|Skeleton)$")
    )
    medium_names = sorted(medium.all_inner_texts())
    tab.locator("#look-rows").get_by_role("button", name=re.compile("^Camera")).click()
    tab.wait_for_timeout(250)
    camera = tab.locator("#look-rows").get_by_role(
        "button", name=re.compile("^(Close-up 85mm|Wide 24mm|Top-down|Low angle|Telephoto|Deep focus)$")
    )
    camera_names = sorted(camera.all_inner_texts())
    check(
        "the second model offers the aids its own sample kept, and not the one it dropped",
        medium_names == ["3D render", "Documentary", "Ink drawing", "Phone snapshot", "Skeleton", "Watercolor"]
        and camera_names == ["Close-up 85mm", "Low angle", "Telephoto", "Top-down", "Wide 24mm"]
        and tab.locator("#templates-toggle").is_visible(),
        f"Medium {medium_names}, Camera {camera_names}",
    )
    tab.click("#backend-toggle")
    tab.wait_for_timeout(250)
    tab.get_by_role("menuitemradio", name=FIRST, exact=True).click()
    tab.wait_for_function(toggle_reads(FIRST), timeout=180000)
    check(
        "the picker switches back, so the server is left as it was found",
        tab.get_by_role("button", name=FIRST, exact=True).is_visible(),
        tab.locator("#backend-toggle").inner_text(),
    )

    # A frame keeps the model that made it, and the switch keeps the strip. Both
    # need two models in one strip: while one model serves the page, the frame's
    # own field and the page's global read the same, so either check would pass
    # whichever way the page worked. Keeping has to be on, or the reload after the
    # switch leaves nothing to compare.
    if not keep_switch(tab).is_checked():
        keep_switch(tab).click()
        tab.wait_for_timeout(500)
    held = frames(tab)
    run_once(tab, "a pear on a wooden table")
    tab.wait_for_timeout(600)
    held += 1
    check(
        "a frame made on one model names that model on its edge",
        frames(tab) == held and edge_model(tab) == edge_of(FIRST),
        f"{frames(tab)} images, edge {edge_model(tab)!r}",
    )
    tab.click("#backend-toggle")
    tab.wait_for_timeout(250)
    tab.get_by_role("menuitemradio", name=SECOND, exact=True).click()
    tab.wait_for_function(toggle_reads(SECOND), timeout=180000)
    tab.wait_for_timeout(1000)
    check(
        "the switch keeps the strip, and the frame still names its own model",
        frames(tab) == held and edge_model(tab) == edge_of(FIRST),
        f"{frames(tab)} images, edge {edge_model(tab)!r}",
    )

    # Six steps and only six: the distilled schedule is the set of nodes the
    # adapter was trained on, so this model has no other step count to ask for.
    run_once(tab, "a pear on a wooden table", steps=6)
    tab.wait_for_timeout(600)
    check(
        "a frame made after the switch names the model that made it",
        frames(tab) == held + 1 and edge_model(tab) == edge_of(SECOND),
        f"{frames(tab)} images, edge {edge_model(tab)!r}",
    )
    # And its file: a name carries the model that made the frame, so one batch of
    # downloads names both models, where the older frame keeps its own while the page
    # is on the newer one. Download all is a real button; the print's own Download is
    # an anchor, which has no button role, and its name carries no frame number.
    downloads = []
    tab.on("download", lambda download: downloads.append(download.suggested_filename))
    tab.get_by_role("button", name="Download all").click()
    tab.wait_for_timeout(5000)
    check(
        "each frame downloads under the name of the model that made it",
        any("-qwen21-generate-" in name for name in downloads)
        and any("-viggle_turbo-generate-" in name for name in downloads),
        str(downloads),
    )
    # The region tool is offered here too, on this model's own measurement. Its brush
    # mounts on a print that is an edit's own reference, so the frame goes through Edit
    # this and the reference comes back off, which is the path the capabilities suite
    # uses for the same question.
    tab.locator("label[for=mode-edit]").click()
    tab.wait_for_timeout(300)
    frame_nodes(tab).first.click()
    tab.wait_for_timeout(300)
    tab.get_by_role("button", name="Edit this", exact=True).click()
    tab.wait_for_timeout(700)
    check(
        "the second model offers the region tool, so its mark can be drawn",
        tab.locator("#canvas canvas").count() >= 1,
        f"{tab.locator('#canvas canvas').count()} canvases on the print",
    )
    for taken in tab.get_by_role("button", name=re.compile("^Remove ")).all():
        taken.click()
    tab.locator("label[for=mode-generate]").click()
    tab.wait_for_timeout(250)

    # A record written before a frame carried its model has none. It must read
    # back without error, and it must not wear the model selected now: that claim
    # is the reading the field exists to remove. One record is copied in without
    # the field, which is the only way to hold an old record on purpose.
    tab.evaluate(
        """async () => {
             const db = await new Promise(function (resolve, reject) {
               const request = indexedDB.open('studio', 1);
               request.onsuccess = function () { resolve(request.result); };
               request.onerror = function () { reject(request.error); };
             });
             const read = db.transaction('images', 'readonly').objectStore('images');
             const all = await new Promise(function (resolve) {
               const request = read.getAll();
               request.onsuccess = function () { resolve(request.result); };
             });
             const old = Object.assign({}, all[0], { id: all[0].id + 9000 });
             delete old.backend;
             db.transaction('images', 'readwrite').objectStore('images').add(old);
           }"""
    )
    tab.reload()
    tab.wait_for_timeout(1500)
    frame_nodes(tab).first.click()
    tab.wait_for_timeout(400)
    check(
        "a frame with no model recorded names none, rather than the one selected now",
        edge_model(tab) == "",
        edge_model(tab) or "no model printed",
    )
    tab.click("#backend-toggle")
    tab.wait_for_timeout(250)
    tab.get_by_role("menuitemradio", name=FIRST, exact=True).click()
    tab.wait_for_function(toggle_reads(FIRST), timeout=180000)

    # The frames made above reached the first tab as well: a kept image goes out
    # on the store's channel and every open tab admits it. The store checks below
    # count the frames in the first tab's strip, so this puts it back at empty.
    page.get_by_role("button", name="Clear all").click()
    page.wait_for_timeout(800)

    # A browser store the page cannot write to has to be reported, not passed over:
    # an image that is silently not kept is lost at the next reload. The stub never
    # fails that way, so the browser's own store is broken underneath the page.
    page.route("**/rewrite", lambda route: route.abort())
    page.fill("#prompt", "a pear")
    page.dispatch_event("#prompt", "input")
    # The id, not the name: this button carries three labels, and the name a role
    # query computes is all of them at once.
    page.click("#rewrite-toggle")
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

    # The page opens the store once and keeps the handle, so after that first
    # moment `indexedDB.open` is never called again and breaking it would prove
    # nothing. What the page asks of the handle is what is broken here instead:
    # the same failure path, reached on the handle the page already holds.
    page.evaluate("""() => {
      window.__realTransaction = IDBDatabase.prototype.transaction;
      IDBDatabase.prototype.transaction = function () { throw new Error('the store refused the request'); };
    }""")
    run_once(page, "a pear the store cannot serve", steps=1)
    page.wait_for_timeout(1500)
    check(
        "a store the handle refuses to serve is reported the same way",
        "did not keep image" in page.locator("#toasts").inner_text(),
        page.locator("#toasts").inner_text().strip()[:100],
    )
    page.evaluate("() => { IDBDatabase.prototype.transaction = window.__realTransaction; }")

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

    # ---- The rewrite writes the box, and the Look rides beside it --------------
    # A Look sentence is the page's own: it was sampled on the model before it was
    # offered, so its wording is the measured part, and the run adds it once at
    # submit. The rewriter is sent the words in the box for the same reason. It used
    # to be sent the Look as well, which put that sentence on the wire twice and made
    # the card name the Look under both of its own terms. A page of its own reads it,
    # so the frames the other checks count do not move.
    rewrite_context = browser.new_context(viewport={"width": 1440, "height": 900})
    written = rewrite_context.new_page()
    written.on("pageerror", lambda error: errors.append("the rewrite page: " + str(error)))
    rewrites_here, runs_here = [], []
    watch_rewrites(written, rewrites_here)
    watch_runs(written, runs_here)
    written.goto(URL)
    written.click("details:has(summary:has-text('Look')) summary")
    written.locator("#look-rows").get_by_role("button", name=re.compile("^Medium")).click()
    written.locator("#look-rows").get_by_role("button", name="Watercolor", exact=True).click()
    watercolour = "Watercolor painting on textured paper, soft washes, visible brush edges."
    written.fill("#prompt", LONG_PROMPT)
    written.dispatch_event("#prompt", "input")
    written.click("#rewrite-toggle")
    written.wait_for_function(
        "() => document.querySelector('#prompt').value.includes('written for the stub')", timeout=120000
    )
    rewritten = written.locator("#prompt").input_value()
    check(
        "a rewrite is asked about the words in the box, and not the Look beside them",
        bool(rewrites_here) and rewrites_here[-1]["prompt"] == LONG_PROMPT,
        rewrites_here[-1]["prompt"][:70] if rewrites_here else "no rewrite was posted",
    )
    set_steps(written, 1)
    written.click("#go")
    wait_until_running(written)
    wait_until_idle(written)
    sent_here = runs_here[-1]["prompt"] if runs_here else ""
    check(
        "a run after a rewrite carries the Look once, and carries what the rewrite wrote",
        sent_here.count(watercolour) == 1 and rewritten in sent_here,
        f"{sent_here.count(watercolour)} times, {sent_here[-80:]!r}",
    )
    written.locator("#stage-bar").get_by_role("button").first.click()
    written.locator("#prompt-sheet").wait_for(state="visible", timeout=10000)
    parts = dict(
        zip(
            written.locator("#prompt-sheet dt").all_inner_texts(),
            written.locator("#prompt-sheet dd").all_inner_texts(),
            strict=True,
        )
    )
    check(
        "the card names the Look apart from the prompt the rewrite wrote",
        watercolour not in parts.get("Prompt", "") and watercolour in parts.get("Look", ""),
        f"prompt {parts.get('Prompt', '')[-60:]!r} / look {parts.get('Look', '')[:60]!r}",
    )
    written.keyboard.press("Escape")
    written.get_by_role("button", name="More actions").click()
    written.get_by_role("menuitem", name="Reuse prompt").click()
    written.wait_for_timeout(400)
    check(
        "Reuse prompt hands back the words typed before the rewrite, and keeps the Look",
        written.locator("#prompt").input_value() == LONG_PROMPT
        and "Watercolor" in (written.locator("#look-values").text_content() or ""),
        f"{written.locator('#prompt').input_value()[:50]!r} / {written.locator('#look-values').text_content()!r}",
    )
    # ---- One press rewrites the box and every marked area with words ----------
    # A marked run's instruction can live in the box, in an area's own row, or in both.
    # One press covers the lot, in the order the form reads: the box's words first, then
    # the areas as they were drawn, and each answer lands where its own words were, so
    # nothing is written twice. Read on the wire and in the two places it lands.
    written.locator("label[for=mode-edit]").click()
    written.get_by_role("button", name=re.compile(r"^generate, seed ")).first.click()
    written.get_by_role("button", name="Edit this").click()
    surface = written.get_by_label("Mark the area to change")
    surface.wait_for(state="visible", timeout=10000)
    written.get_by_role("button", name="Mark in orange").click()
    drawn = surface.bounding_box()
    for x1, y1, x2, y2 in ((90, 90, 160, 150), (200, 200, 250, 250)):
        written.mouse.move(drawn["x"] + x1, drawn["y"] + y1)
        written.mouse.down()
        written.mouse.move(drawn["x"] + x2, drawn["y"] + y2, steps=8)
        written.mouse.up()
        written.wait_for_timeout(200)
        if (x1, y1) == (90, 90):
            written.get_by_role("button", name="Mark in red").click()
    written.get_by_label("What changes in the orange area?").fill("make it a stone wall")
    written.get_by_label("What changes in the red area?").fill("warm the tiles")
    written.fill("#prompt", "a pear on a table")
    written.dispatch_event("#prompt", "input")
    before = len(rewrites_here)
    written.click("#rewrite-toggle")
    # The card's own Edit this switches the mode, and that empties the prompt and the Look,
    # so it is locked for the length of the press and comes back when the press ends.
    written.wait_for_timeout(700)
    locked = written.get_by_role("button", name="Edit this")
    check(
        "the card's Edit this is locked while the rewriter writes",
        locked.is_disabled(),
        f"disabled {locked.is_disabled()}, title {locked.get_attribute('title')!r}",
    )
    # The readout is the only live word on a press, and a press over three parts takes about
    # three times as long as one. It names the part, its place, and the whole press: it used
    # to quote the one-part time for every press, whatever its size.
    said = ""
    for _ in range(40):
        written.wait_for_timeout(200)
        said = written.locator("#status").inner_text().strip()
        if " of 3" in said:
            break
    check(
        "the readout names the part and what the whole press costs",
        written.locator("#status").is_visible() and " of 3" in said and "1 min 30s in all" in said,
        f"visible {written.locator('#status').is_visible()}, {said!r}",
    )
    # A run would free the rewriter the press is writing with, so the run waits for the press.
    # Cmd+Enter obeys the same rule for free, since it asks the button's own disabled state.
    check(
        "the run button waits for the press, and says so",
        written.locator("#go").is_disabled()
        and "Wait for the rewrite to finish" in written.locator("#go-sub").inner_text(),
        f"disabled {written.locator('#go').is_disabled()}, reason {written.locator('#go-sub').inner_text()!r}",
    )
    frames_before = written.get_by_role("button", name=re.compile(r"^(generate|edit), seed ")).count()
    written.keyboard.press("Meta+Enter")
    written.wait_for_timeout(1500)
    frames_after = written.get_by_role("button", name=re.compile(r"^(generate|edit), seed ")).count()
    check(
        "Cmd+Enter waits for the press like a click does",
        frames_after == frames_before,
        f"{frames_before} frames before, {frames_after} after",
    )
    check(
        "the card's own menu waits for the press too",
        written.get_by_role("button", name="More actions").first.is_disabled(),
        written.get_by_role("button", name="More actions").first.get_attribute("title"),
    )
    written.wait_for_function(
        "() => document.querySelector('[aria-label=\"What changes in the red area?\"]')"
        ".value.includes('written for the stub')",
        timeout=180000,
    )
    written.wait_for_timeout(300)
    check(
        "and the card's Edit this comes back when the press ends",
        written.get_by_role("button", name="Edit this").is_enabled(),
        written.get_by_role("button", name="Edit this").get_attribute("title"),
    )
    pressed = [item["prompt"] for item in rewrites_here[before:]]
    check(
        "one press rewrites the box and each marked area, in the order the form reads",
        pressed == ["a pear on a table", "make it a stone wall", "warm the tiles"],
        " | ".join(pressed)[:110],
    )
    rows = [written.get_by_label(f"What changes in the {colour} area?").input_value() for colour in ("orange", "red")]
    after = " A longer version of it, written for the stub."
    check(
        "each answer lands where its own words were, and the box keeps its own",
        written.locator("#prompt").input_value() == "a pear on a table" + after
        and rows == ["make it a stone wall" + after, "warm the tiles" + after],
        f"box {written.locator('#prompt').input_value()[:40]!r} / rows {rows}",
    )
    # The press is offered on an empty box as long as an area carries words, which is the
    # state a marked run is in: the rows are the instruction, and the box has none.
    written.fill("#prompt", "")
    written.dispatch_event("#prompt", "input")
    check(
        "a press is offered when only the marked areas carry words",
        written.locator("#rewrite-toggle").is_enabled(),
        written.locator("#rewrite-toggle").get_attribute("title"),
    )

    # A cancel stops the press where it is: the areas already written keep their answer, and the
    # ones after it keep the words they had. Two areas are needed, so both go back to what they
    # said and the press is stopped once the first answer has landed.
    written.get_by_label("What changes in the orange area?").fill("make it a stone wall")
    written.get_by_label("What changes in the red area?").fill("warm the tiles")
    written.wait_for_timeout(200)
    written.click("#rewrite-toggle")
    written.wait_for_function(
        "() => document.querySelector('[aria-label=\"What changes in the orange area?\"]')"
        ".value.includes('written for the stub')",
        timeout=180000,
    )
    if written.locator("#rewrite-toggle").inner_text().strip() == "Cancel":
        written.click("#rewrite-toggle")
    written.wait_for_function("() => !document.body.classList.contains('rewriting')", timeout=180000)
    written.wait_for_timeout(500)
    orange = written.get_by_label("What changes in the orange area?").input_value()
    red = written.get_by_label("What changes in the red area?").input_value()
    check(
        "a cancel stops the press where it is, and the areas after it keep their words",
        "written for the stub" in orange and red == "warm the tiles",
        f"orange {orange[-30:]!r}, red {red!r}",
    )

    # A reload forgets the press, so the page must come back with no claim on it. The page is
    # only asked to draw again, which is what it does on a load.
    written.reload()
    written.wait_for_timeout(1200)
    check(
        "a reload in the middle of a press leaves no claim behind",
        "rewriting" not in written.evaluate("() => document.body.className")
        and written.locator("#rewrite-toggle").inner_text().strip() == "Rewrite",
        written.evaluate("() => document.body.className"),
    )
    rewrite_context.close()

    # ---- One prompt over several images ------------------------------------------
    # Several references mean one picture in generate, and in edit they can mean one result
    # each. The mode declares whether the page may offer that choice, and the choice is what
    # the count is charged against: the count is what each reference gets. A page of its own
    # reads it, so the frames the other checks count do not move.
    batch_context = browser.new_context(viewport={"width": 1440, "height": 900})
    batched = batch_context.new_page()
    batched.on("pageerror", lambda error: errors.append("the batch page: " + str(error)))
    runs_here = []
    watch_runs(batched, runs_here)
    batched.goto(URL)
    set_steps(batched, 1)
    batched.click("#count-toggle")
    batched.wait_for_timeout(250)
    batched.locator("#count-menu button").nth(1).click()
    batched.fill("#prompt", "a pear on a table")
    batched.dispatch_event("#prompt", "input")
    batched.click("#go")
    wait_until_running(batched)
    wait_until_idle(batched)
    batched.wait_for_timeout(800)
    frames_here = batched.get_by_role("button", name=re.compile(r"^(generate|edit), seed "))
    check(
        "the count menu makes as many images as it says",
        frames_here.count() == 2,
        f"{frames_here.count()} frames",
    )
    # Both of them, one as the image to edit and one as a second reference.
    frames_here.first.click()
    batched.get_by_role("button", name="Edit this").click()
    batched.wait_for_timeout(400)
    frames_here.nth(1).click()
    batched.get_by_role("button", name="More actions").click()
    batched.wait_for_timeout(250)
    batched.get_by_role("menuitem", name="Use as reference").click()
    batched.wait_for_timeout(400)
    check(
        "the edit form offers what several images may mean, and says which way it is set",
        batched.locator("#each-choice").is_visible() and "single picture" in batched.locator("#each-note").inner_text(),
        batched.locator("#each-note").inner_text(),
    )
    batched.locator("label[for=each-each]").click()
    batched.wait_for_timeout(300)
    check(
        "choosing one edit each says how many results that is",
        "2 results" in batched.locator("#each-note").inner_text(),
        batched.locator("#each-note").inner_text(),
    )
    # The count is what each reference gets, so a count above one multiplies the results, and
    # the caption has to say the same number the button and the run make.
    batched.click("#count-toggle")
    batched.wait_for_timeout(250)
    batched.locator("#count-menu button").nth(1).click()
    batched.wait_for_timeout(300)
    check(
        "a count above one multiplies what the caption promises",
        "4 results" in batched.locator("#each-note").inner_text(),
        batched.locator("#each-note").inner_text(),
    )
    batched.click("#count-toggle")
    batched.wait_for_timeout(250)
    batched.locator("#count-menu button").first.click()
    batched.wait_for_timeout(300)

    # A batch writes each image its own instruction, read from that image, so the press is
    # the user's to make here. It is offered, and the note says what it writes, because the
    # four answers of a batch cost four times one.
    batched.fill("#prompt", "make them chihuahua")
    batched.dispatch_event("#prompt", "input")
    batched.wait_for_timeout(300)
    check(
        "a batch offers the press, and the note says what it writes",
        batched.locator("#rewrite-toggle").is_enabled()
        and "a row adds what that one needs" in batched.locator("#each-note").inner_text(),
        f"enabled {batched.locator('#rewrite-toggle').is_enabled()}, "
        f"note {batched.locator('#each-note').inner_text()[-70:]!r}",
    )
    batched.locator("label[for=each-all]").click()
    batched.wait_for_timeout(300)
    check(
        "composed, the press is offered again",
        batched.locator("#rewrite-toggle").is_enabled(),
        batched.locator("#rewrite-toggle").get_attribute("title"),
    )
    batched.locator("label[for=each-each]").click()
    batched.wait_for_timeout(300)
    check(
        "and back to a batch, with the words still in the box",
        batched.locator("#rewrite-toggle").is_enabled()
        and batched.locator("#prompt").input_value() == "make them chihuahua",
        f"enabled {batched.locator('#rewrite-toggle').is_enabled()}, box {batched.locator('#prompt').input_value()!r}",
    )

    batched.fill("#prompt", "make the background a stone wall")
    batched.dispatch_event("#prompt", "input")
    check(
        "the run button promises the images the whole batch makes",
        "2 images" in batched.locator("#go-sub").inner_text(),
        batched.locator("#go-sub").inner_text(),
    )
    before_here = frames_here.count()
    batched.click("#go")
    wait_until_running(batched)
    wait_until_idle(batched)
    batched.wait_for_timeout(1000)
    check(
        "one press gives one result for each reference",
        frames_here.count() == before_here + 2,
        f"{before_here} before, {frames_here.count()} after",
    )
    # Each result came from one of the two references, so each has a source to wipe against:
    # the composed edit cannot, which is why it has none.
    wipes = []
    for index in range(frames_here.count()):
        frames_here.nth(index).click()
        batched.wait_for_timeout(250)
        wipes.append(batched.get_by_role("button", name="Compare").count())
    check(
        "each result of the batch offers its own before and after",
        wipes == [1, 1, 0, 0],
        f"wipes per frame {wipes}",
    )
    # A result of the batch edited one of the two pictures, so its card names that one. Naming
    # both, or naming the same one twice, is what this reads: the wipe existing is not enough.
    edited = []
    for index in range(2):
        frames_here.nth(index).click()
        batched.wait_for_timeout(300)
        edited.append(stage_text(batched))
    check(
        "each result names the picture it edited, and they are not the same one",
        len({text for text in edited}) == 2 and all("Edited from" in text for text in edited),
        f"{edited[0][:50]!r} / {edited[1][:50]!r}",
    )
    # The choice belongs to the mode that declares it, and it goes back with the words when the
    # mode changes, or a stale choice would outlive the references it was made about.
    batched.click("label[for=mode-generate]")
    batched.wait_for_timeout(300)
    batched.click("label[for=mode-edit]")
    batched.wait_for_timeout(300)
    check(
        "a mode switch puts the choice back with the words it was made about",
        batched.locator("#each-all").is_checked() or not batched.locator("#each-choice").is_visible(),
        f"all checked {batched.locator('#each-all').is_checked()}, visible {batched.locator('#each-choice').is_visible()}",
    )

    batch_context.close()

    # ---- One instruction for each image of a batch -----------------------------
    # A batch applies one instruction to every image, and the pictures are what differ. The
    # rewriter reads one picture at a time, so a press writes one instruction for each image,
    # from that image. The stub's rewriter echoes what it is given, so the wire and the rows
    # both say what a press was asked and what it wrote back.
    instructions = browser.new_context(viewport={"width": 1440, "height": 900})
    per_image = instructions.new_page()
    per_image.goto(URL)
    set_steps(per_image, 1)
    per_image.locator("label[for=mode-edit]").click()
    per_image.set_input_files("#reference", [str(SCRATCH / "reference-a.png"), str(SCRATCH / "reference-b.png")])
    per_image.get_by_role("img", name="reference-a.png").wait_for(state="visible", timeout=10000)
    per_image.wait_for_timeout(300)
    check(
        "no instruction rows while the images are composed",
        per_image.locator("#each-rows").is_hidden() and per_image.locator("#each-rows textarea").count() == 0,
        f"hidden {per_image.locator('#each-rows').is_hidden()}",
    )
    per_image.locator("label[for=each-each]").click()
    per_image.wait_for_timeout(300)
    rows = per_image.locator("#each-rows textarea")
    check(
        "one row per image comes with the choice, each named by its own picture",
        per_image.locator("#each-rows").is_visible()
        and rows.count() == 2
        and rows.nth(0).get_attribute("aria-label") == "What image 1 is asked"
        and rows.nth(1).get_attribute("aria-label") == "What image 2 is asked"
        and per_image.evaluate(
            """() => {
                 const rows = [...document.querySelectorAll('#each-rows .each-thumb')].map(img => img.src);
                 const refs = [...document.querySelectorAll('#thumbs .thumb img')].map(img => img.src);
                 return JSON.stringify(rows) === JSON.stringify(refs);
               }"""
        ),
        f"{rows.count()} rows",
    )
    # Drawn tall enough for the line each one holds, before the press fills them. A textarea
    # measures itself off its own content and has none while it is still detached, so one grown
    # before it is in the page takes the height of nothing. `offsetHeight` is the box with its
    # border, which is what `scrollHeight` is measured against.
    lines = per_image.eval_on_selector_all(
        "#each-rows textarea", "els => els.map(el => [el.offsetHeight, el.scrollHeight])"
    )
    check(
        "each instruction row is drawn as tall as its own line, before it is filled",
        all(abs(one - other) <= 2 for one, other in lines),
        f"{lines}",
    )
    words = "make the background a stone wall"
    per_image.fill("#prompt", words)
    per_image.dispatch_event("#prompt", "input")
    per_image.wait_for_timeout(250)
    check(
        "the press is offered for a batch, and says what it writes",
        per_image.locator("#rewrite-toggle").is_enabled()
        and "each image" in (per_image.locator("#rewrite-toggle").get_attribute("title") or ""),
        per_image.locator("#rewrite-toggle").get_attribute("title"),
    )
    asked = []
    watch_rewrites(per_image, asked)
    per_image.click("#rewrite-toggle")
    per_image.wait_for_function(
        "() => [...document.querySelectorAll('#each-rows textarea')].every(row => row.value.trim() !== '')",
        timeout=60000,
    )
    per_image.wait_for_function(VERB_IS_REWRITE, timeout=60000)
    pictures = [json.loads(post["references"]) for post in asked]
    check(
        "the press asks about one image at a time, and about each image once",
        len(asked) == 2
        and all(len(images) == 1 for images in pictures)
        and pictures[0] != pictures[1]
        and all(post["prompt"] == words for post in asked),
        f"{len(asked)} rewrites, {[len(images) for images in pictures]} picture(s) each",
    )
    check(
        "each answer lands in its own image's row",
        all(rows.nth(index).input_value().startswith(words) for index in range(2)),
        f"{rows.nth(0).input_value()[:40]!r} / {rows.nth(1).input_value()[:40]!r}",
    )
    # The rows are the user's to correct, and a run carries each image its own. The images are
    # the stub's, so the instruction each one was sent is read on the wire.
    rows.nth(0).fill("make the wall stone")
    rows.nth(0).dispatch_event("input")
    per_image.wait_for_timeout(250)
    second = rows.nth(1).input_value()
    runs = []
    watch_runs(per_image, runs)
    per_image.click("#go")
    wait_until_running(per_image)
    wait_until_idle(per_image)
    per_image.wait_for_timeout(600)
    prompts = [post.get("prompt") for post in runs]
    check(
        "each image of the batch is sent its own instruction, with the words in the box leading",
        len(runs) == 2 and prompts[0] == words + ". make the wall stone" and prompts[1] == words + ". " + second,
        f"{prompts}",
    )
    # A batch whose every image carries words of its own is a whole instruction with an empty
    # box, which is what a marked run already allows. One row still empty holds the run back.
    per_image.set_input_files("#reference", [str(SCRATCH / "reference-a.png"), str(SCRATCH / "reference-b.png")])
    per_image.get_by_role("img", name="reference-a.png").wait_for(state="visible", timeout=10000)
    per_image.locator("label[for=each-each]").click()
    per_image.wait_for_timeout(300)
    rows = per_image.locator("#each-rows textarea")
    # Both rows are set, one of them to nothing: the same two pictures come back with the rows
    # they were written from, so an empty row has to be asked for and not assumed.
    rows.nth(0).fill("only the sky")
    rows.nth(0).dispatch_event("input")
    rows.nth(1).fill("")
    rows.nth(1).dispatch_event("input")
    per_image.wait_for_timeout(250)
    check(
        "one row still empty holds the run back, and says so",
        not per_image.locator("#go").is_enabled() and "each image" in per_image.inner_text("#go-sub"),
        per_image.inner_text("#go-sub"),
    )
    rows.nth(1).fill("only the floor")
    rows.nth(1).dispatch_event("input")
    set_steps(per_image, 1)
    per_image.wait_for_timeout(250)
    check(
        "a batch of rows runs with the box empty",
        per_image.locator("#go").is_enabled(),
        per_image.inner_text("#go-sub"),
    )
    bare = []
    watch_runs(per_image, bare)
    per_image.click("#go")
    wait_until_running(per_image)
    wait_until_idle(per_image)
    per_image.wait_for_timeout(600)
    sent = [post.get("prompt") for post in bare]
    check(
        "and each image is sent its own words alone",
        sent == ["only the sky", "only the floor"],
        f"{sent}",
    )
    # A count above one asks for several results from every image, so the requests outnumber
    # the images and the place comes back around. Two images and a count of two is four
    # requests over two rows, and the third takes the first row's words again.
    per_image.set_input_files("#reference", [str(SCRATCH / "reference-a.png"), str(SCRATCH / "reference-b.png")])
    per_image.get_by_role("img", name="reference-a.png").wait_for(state="visible", timeout=10000)
    per_image.locator("label[for=each-each]").click()
    per_image.wait_for_timeout(300)
    per_image.click("#count-toggle")
    per_image.wait_for_timeout(250)
    per_image.locator("#count-menu button").nth(1).click()
    per_image.wait_for_timeout(250)
    rows = per_image.locator("#each-rows textarea")
    rows.nth(0).fill("a stone wall")
    rows.nth(0).dispatch_event("input")
    rows.nth(1).fill("warmer light")
    rows.nth(1).dispatch_event("input")
    per_image.fill("#prompt", words)
    per_image.dispatch_event("#prompt", "input")
    set_steps(per_image, 1)
    per_image.wait_for_timeout(250)
    more = []
    watch_runs(per_image, more)
    per_image.click("#go")
    wait_until_running(per_image)
    wait_until_idle(per_image)
    per_image.wait_for_timeout(600)
    prompts = [post.get("prompt") for post in more]
    check(
        "a count above one asks each image again, and its own words come back around",
        prompts
        == [words + ". a stone wall", words + ". warmer light", words + ". a stone wall", words + ". warmer light"],
        f"{prompts}",
    )
    # A press right after a run, which is the state that run leaves: the form is emptied, the
    # references go with it, and the rows are built again from the pictures that come back. That
    # sequence was missing here and a run of `verify_batch.py` on the office ended with a press
    # that wrote nothing at all, so the wiring is read here where it costs no GPU.
    per_image.set_input_files("#reference", [str(SCRATCH / "reference-a.png"), str(SCRATCH / "reference-b.png")])
    per_image.get_by_role("img", name="reference-a.png").wait_for(state="visible", timeout=10000)
    per_image.locator("label[for=each-each]").click()
    per_image.fill("#prompt", words)
    per_image.dispatch_event("#prompt", "input")
    per_image.wait_for_timeout(300)
    rows = per_image.locator("#each-rows textarea")
    pressed_again = []
    watch_rewrites(per_image, pressed_again)
    per_image.click("#rewrite-toggle")
    # The rows already hold the words this press is about to replace, so "every row is filled" is
    # true the moment it is asked and the press gets read before it has posted: one request of
    # two. The wait is for the press to be over, which the body says and the stale rows do not.
    with contextlib.suppress(Exception):
        per_image.wait_for_function(
            "() => !document.body.classList.contains('rewriting')"
            " && [...document.querySelectorAll('#each-rows textarea')].every(row => row.value.trim() !== '')",
            timeout=90000,
        )
    per_image.wait_for_function(VERB_IS_REWRITE, timeout=60000)
    check(
        "a press after a run writes into the rows it built again",
        len(pressed_again) == 2 and all(rows.nth(place).input_value().strip() for place in range(2)),
        f"{len(pressed_again)} rewrites, rows {[rows.nth(place).input_value()[:20] for place in range(2)]}"
        + (
            ""
            if len(pressed_again) == 2 and all(rows.nth(place).input_value().strip() for place in range(2))
            else ". The page said: "
            + (per_image.locator("#toasts").inner_text().strip().replace("\n", " ") or "nothing")
        ),
    )
    instructions.close()

    # ---- What the run button is called, and what a role query reaches ----------
    # The button's name is composed from the DOM, not from the cascade: the page
    # sets `hidden` on the labels it is not using, so a stylesheet that fails to
    # load still leaves exactly one label in the name. It used to be the
    # stylesheet that hid them, and a refused one left the name as
    # "GenerateEdit Cancel Stopping…", which is noise to a screen reader and
    # matched no verb. The page is loaded again with the stylesheet refused, so
    # this check cannot pass on the cascade by accident.
    plain_context = browser.new_context(viewport={"width": 1440, "height": 900})
    plain_context.route("**/page/page.css", lambda route: route.abort())
    plain = plain_context.new_page()
    plain.goto(URL)
    set_steps(plain, 1)
    plain.fill("#prompt", "a pear on a table")
    plain.dispatch_event("#prompt", "input")
    plain.click("#go")
    plain.locator(RUNNING).wait_for(state="visible", timeout=30000)
    check(
        "the run button is called Cancel with no stylesheet at all",
        plain.get_by_role("button", name="Cancel", exact=True).count() == 1,
        plain.locator("#go").aria_snapshot(),
    )
    check(
        "the run readout is a status a role query reaches while a run goes",
        "status" in plain.get_by_role("status").evaluate_all("nodes => nodes.map((node) => node.id)"),
        str(plain.get_by_role("status").evaluate_all("nodes => nodes.map((node) => node.id)")),
    )
    plain.locator(RUNNING).wait_for(state="hidden", timeout=600000)

    # The other half of the row-name pair. A row's name is its own name and then
    # its pick, and the stylesheet is what puts a space between them, so a
    # refused one reads them as one word. This is the check that catches a text
    # node added between the two, which no check with the stylesheet in place
    # can see.
    plain.click("#look summary")
    plain.locator("#look-rows").get_by_role("button", name=re.compile("^Light")).click()
    plain.locator("#look-rows").get_by_role("button", name="Overcast", exact=True).click()
    check(
        "a Look row's name is the row and its pick as one word with no stylesheet at all",
        plain.get_by_role("button", name="LightOvercast", exact=True).count() == 1,
        plain.locator("#look-rows").aria_snapshot().replace("\n", " ")[:120],
    )
    plain_context.close()

    # ---- The order several files are picked in ---------------------------------
    # A browser reads the files of one pick one at a time, and they finish in their own order,
    # so a list built as each read lands can hold them grouped by how long the read took. It is
    # built from the picks instead. On a real machine, four photographs picked at once put two
    # of them in the wrong places, which is what this guards, in its own place because it needs
    # four references held and the blocks above count them.
    #
    # What it traps, measured against a copy of this tree with the old read loop in it: 2 of 12
    # uploads came back in the wrong order, and the wrong order looks like ["reference-b.png",
    # "reference-b.png", "reference-a.png", "reference-a.png"]. Against this tree, 0 of 12.
    order_context = browser.new_context(viewport={"width": 1440, "height": 900})
    picked_in_order = order_context.new_page()
    picked_in_order.goto(URL)
    picked_in_order.locator(IDLE).wait_for(state="visible", timeout=60000)
    picked_in_order.locator("label[for=mode-edit]").click()
    wanted = ["reference-a.png", "reference-b.png", "reference-a.png", "reference-b.png"]
    picked_in_order.set_input_files("#reference", [str(SCRATCH / name) for name in wanted])
    picked_in_order.wait_for_function("() => document.querySelectorAll('#thumbs .thumb').length === 4", timeout=10000)
    held = picked_in_order.eval_on_selector_all("#thumbs .thumb", "els => els.map(el => el.title)")
    check(
        "several files picked in one go land in the order they were picked",
        held == wanted,
        f"{held}",
    )
    order_context.close()

    check("no page errors", not errors, str(errors)[:200])
    if session is not None:
        js_coverage.report(session)
    browser.close()

shutil.rmtree(SCRATCH, ignore_errors=True)

failed = [name for name, passed in results if not passed]
print(f"\n{len(results) - len(failed)}/{len(results)} passed", "FAILED: " + ", ".join(failed) if failed else "")
sys.exit(1 if failed else 0)
