"""Real-run check of the batch: several references, and one result each.

It makes four pictures of four different subjects, then edits all four twice. The first run
takes one instruction for every image, in the user's own words, which is what a batch did
before the press could write for it. The second is pressed first, so each image is given its
own instruction, written from that image.

The identity of each result is read off the wire: every response names the reference it
edited, and every request of the chain names the image it asked for. The pairing between a
result and the picture it came from is read off the pixels, because the wire says which
reference a request carried and only the picture says whether the engine obeyed it. That
second run's instruction keeps every scene as it is, so a result that took another picture's
scene is visible as a background that is nearer to another picture than to its own.

This is the batch's only check on real pixels. The stub reads its wiring, in `verify_ui.py`:
what a press does, which request carries which words, and how the rows follow a count above
one. Nothing here duplicates that.

Every binding is a role, an accessible name, a label association, or an id the page publishes.
One is left: LEFT: `data-reference` on the run's own `.item`, which the server writes for each
image of a batch and no role reaches.

Usage: uv run --with playwright python tests/e2e/verify_batch.py <port>
"""

import base64
import contextlib
import re
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright

PORT = sys.argv[1]
OUT = tempfile.mkdtemp(prefix="verify-batch-") + "/"
print("Pictures:", OUT)
results = []

RUN_IDLE = "#go[data-state='idle']"
EDIT_FRAMES = "#strip .frame[aria-label^='edit, seed ']"
# Four subjects, so an instruction written from the wrong picture shows up as a row that
# names another picture's subject.
SOURCE_PROMPTS = [
    "a golden retriever sitting on green grass, photo",
    "a black cat on a wooden windowsill, photo",
    "a grey rabbit in a garden, photo",
    "a red parrot on a tree branch, photo",
]
SUBJECTS = {
    0: ("retriever", "dog", "grass"),
    1: ("cat", "windowsill"),
    2: ("rabbit", "garden"),
    3: ("parrot", "branch"),
}
# What every image is asked when the batch is not pressed, and what the press is asked for
# when it is. The second keeps each scene as it is, which is what makes the pairing between a
# result and its picture readable: a result that took another picture's scene would show.
PLAIN_WORDS = "make it a chihuahua sitting in a dog bed"
KEEPING_WORDS = "keep everything in the picture exactly as it is, and only change the animal into a chihuahua"

# The background ring, where the scene is and the subject is not, at a size the two engines
# agree on. The difference is the mean absolute difference of those rings, 0 to 255.
SIDE = 64
RING = 0.12


def check(name, passed, detail=""):
    results.append((name, passed))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def parse_post(request):
    """One posted form, as a plain dict of single values."""
    return {name: values[0] for name, values in urllib.parse.parse_qs(request.post_data or "").items()}


def wait_idle(page):
    page.locator(RUN_IDLE).wait_for(state="visible", timeout=900000)
    time.sleep(0.5)


def save_frame(page, locator, path):
    """One kept frame's own pixels, off the blob the strip draws it from."""
    handle = locator.element_handle()
    if handle is None:
        raise RuntimeError(f"no frame element for {path}")
    b64 = page.evaluate(
        """async (img) => {
             const blob = await (await fetch(img.src)).blob();
             const bytes = new Uint8Array(await blob.arrayBuffer());
             let text = '';
             for (let i = 0; i < bytes.length; i += 0x8000) {
               text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
             }
             return btoa(text);
           }""",
        handle,
    )
    Path(path).write_bytes(base64.b64decode(b64))


def source_numbers(page, folder):
    """The source behind each instruction row, read off the picture that row carries.

    The list is ordered by when each file finished reading and not by when it was picked, so
    a row's place says nothing about which picture it holds. The picture itself does.
    """
    thumbs = page.eval_on_selector_all("#each-rows .each-thumb", "els => els.map(el => el.src)")
    known = {}
    for path in sorted(Path(folder).glob("source-*.png")):
        known["data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()] = (
            int(path.stem.split("-")[1]) - 1
        )
    return [known.get(thumb, -1) for thumb in thumbs]


def ring(path):
    """The border strip of a picture, which is its scene and not its subject."""
    image = Image.open(path).convert("RGB").resize((SIDE, SIDE))
    band = int(SIDE * RING)
    strips = [
        image.crop((0, 0, SIDE, band)),
        image.crop((0, SIDE - band, SIDE, SIDE)),
        image.crop((0, 0, band, SIDE)),
        image.crop((band, 0, SIDE, SIDE)),
    ]
    out = Image.new("RGB", (SIDE, band * 4))
    for index, strip in enumerate(strips):
        out.paste(strip, (0, band * index))
    return out


def nearest_source(result, sources):
    """Which source's scene the result kept, and its distance from every one of them."""
    distances = []
    for source in sources:
        stat = ImageStat.Stat(ImageChops.difference(result, source))
        distances.append(sum(stat.mean) / 3)
    return distances.index(min(distances)), [round(value, 1) for value in distances]


def names(answer, place):
    """Which of a picture's own words an answer carries. A reader, not a judgement: "dog" inside
    "dog bed" counts, and that is the noise on the measurement line."""
    return [word for word in SUBJECTS[place] if word in answer.lower()]


def names_other(answer, place):
    """Another picture's subject words, which an answer about this picture should not carry."""
    return [word for other, words in SUBJECTS.items() if other != place for word in words if word in answer.lower()]


def few_steps(page):
    """The step count this check needs, set on the run that is about to use it.

    The field goes back to the mode's own default when a run empties the form, which is 40
    on this backend, so a phase cannot rely on the phase before it. Eight steps is enough
    for the answer read here: which picture each result came from.
    """
    panel = page.locator("#advanced")
    if not panel.evaluate("el => el.open"):
        page.click("#advanced summary")
    page.fill("#steps", "8")
    page.dispatch_event("#steps", "input")
    if panel.evaluate("el => el.open"):
        page.click("#advanced summary")


def watch(page, posts, bodies):
    page.on(
        "request",
        lambda request: (
            posts.append(parse_post(request))
            if request.method == "POST" and request.url.endswith("/generate")
            else None
        ),
    )
    page.on(
        "response",
        lambda response: (
            bodies.append(response)
            if response.request.method == "POST" and response.url.endswith("/generate")
            else None
        ),
    )


def requests_of(posts):
    """Every request of the batch, keyed by the image it asked for.

    The form's own request is the first image and carries no index, and each chain
    placeholder after it names its own. The index counts requests, so a count above one
    asks for several results from every image and comes back around.
    """
    by_index = {}
    for post in posts:
        by_index["1" if not post.get("index") else post["index"]] = post.get("prompt")
    return by_index


def write_results(bodies, folder):
    """Every result, written out beside the source it edits, and the references it named."""
    claims = []
    for response in bodies:
        try:
            text = response.text()
        except Exception as error:
            check("a response body could be read", False, str(error))
            continue
        claims += re.findall(r'data-reference="(-?\d+)"', text)
        for reference, b64 in re.findall(
            r'data-reference="(-?\d+)"[^>]*><img src="data:image/png;base64,([^"]+)"', text
        ):
            Path(f"{folder}out-ref{reference}.png").write_bytes(base64.b64decode(b64))
    return claims


def upload(page, paths):
    page.locator("#reference").set_input_files([str(path) for path in paths])
    page.wait_for_function(f"() => document.querySelectorAll('#thumbs .thumb').length === {len(paths)}", timeout=30000)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark").new_page()
    errors = []
    page.on("console", lambda message: message.type == "error" and errors.append(message.text))
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"http://127.0.0.1:{PORT}/")
    page.locator(RUN_IDLE).wait_for(state="visible", timeout=120000)

    # The smallest shape the form offers: this check is about which picture each result came
    # from, and a bigger one costs the same GPU time for the same answer.
    page.click("#advanced summary")
    page.locator("#tier-sizes").get_by_role("button").first.click()

    for index, prompt in enumerate(SOURCE_PROMPTS, start=1):
        few_steps(page)
        page.fill("#prompt", prompt)
        page.dispatch_event("#prompt", "input")
        page.click("#go")
        wait_idle(page)
        save_frame(page, page.locator("#strip .frame.selected img").first, f"{OUT}source-{index}.png")
    sources = sorted(Path(OUT).glob("source-*.png"))
    check(
        "four different pictures were made to edit",
        len(sources) == 4 and len({path.read_bytes() for path in sources}) == 4,
        f"{len(sources)} pictures",
    )

    page.click("label[for=mode-edit]")

    # ---- The batch that is not pressed: one instruction for every image ----------------
    upload(page, sources)
    page.click("#each-choice label[for=each-each]")
    page.fill("#prompt", PLAIN_WORDS)
    page.dispatch_event("#prompt", "input")
    page.wait_for_timeout(300)
    posts = []
    bodies = []
    watch(page, posts, bodies)
    few_steps(page)
    page.click("#go")
    wait_idle(page)

    sent = requests_of(posts)
    check(
        "the batch walked the four references in order",
        sorted(sent) == ["1", "2", "3", "4"] and len(posts) == 4,
        f"{len(posts)} requests, images {sorted(sent)}",
    )
    check(
        "without a press, every image is given the words in the box",
        len(set(sent.values())) == 1 and set(sent.values()) == {PLAIN_WORDS},
        f"{sorted(set(sent.values()))}",
    )
    claims = write_results(bodies, OUT)
    check(
        "each result names its own reference, and no two name the same",
        sorted(claims) == ["0", "1", "2", "3"],
        f"references {claims}",
    )
    check(
        "one result per reference was kept",
        page.locator(EDIT_FRAMES).count() == 4,
        f"{page.locator(EDIT_FRAMES).count()} edit frames",
    )
    captions = []
    for index in range(page.locator(EDIT_FRAMES).count()):
        page.locator(EDIT_FRAMES).nth(index).click()
        page.wait_for_timeout(200)
        captions.append(page.locator("#stage-bar .prompt-line").inner_text().strip())
    check(
        "every card records the instruction its own image was given",
        all(text == PLAIN_WORDS for text in captions),
        f"{captions[:1]}",
    )

    # ---- The batch that is pressed: one instruction for each image ---------------------
    # The run above emptied the form, references and all, so the four go back.
    page.click("label[for=mode-edit]")
    upload(page, sources)
    page.click("#each-choice label[for=each-each]")
    page.fill("#prompt", KEEPING_WORDS)
    page.dispatch_event("#prompt", "input")
    page.wait_for_timeout(300)
    rows = page.locator("#each-rows textarea")
    posts = []
    bodies = []
    watch(page, posts, bodies)

    few_steps(page)
    started = time.monotonic()
    page.click("#rewrite-toggle")
    # A press that never filled a row is reported by the check below and not raised here,
    # so the four answers, the requests and the pictures are all read either way.
    with contextlib.suppress(Exception):
        page.wait_for_function(
            "() => [...document.querySelectorAll('#each-rows textarea')].every(row => row.value.trim() !== '')",
            timeout=900000,
        )
    page.wait_for_function(
        "() => document.getElementById('rewrite-toggle').innerText.trim() === 'Rewrite'", timeout=900000
    )
    pressed = time.monotonic() - started
    answers = [rows.nth(place).input_value().strip() for place in range(rows.count())]
    pictures = source_numbers(page, OUT)
    check(
        "the press wrote an instruction for every image",
        len(answers) == 4 and all(answers),
        f"{sum(1 for answer in answers if answer)} of 4 filled in {pressed:.0f}s",
    )
    # Four answers, one per picture, and no two the same. That is what a press per image
    # guarantees and what a single paragraph over four pictures cannot: the fault this guards
    # gave four copies of one answer.
    #
    # Whether an answer *names* the picture it was written from is read here and not asserted.
    # It is a second model's wording: three runs of this check named four, four and three of
    # four, so an assertion on it would fail on the model's luck rather than on the page. The
    # printed line is the measurement, and the claim that an instruction is obeyed is the
    # pairing check below, which reads the pixels and has held every time.
    named = [names(answers[place], pictures[place]) for place in range(4)]
    check(
        "the press wrote four different instructions, one for each picture",
        len(answers) == 4 and all(answers) and len(set(answers)) == 4 and len(set(pictures)) == 4,
        f"{len(set(answers))} answers for {len(set(pictures))} pictures, in {pressed:.0f}s",
    )
    print("  an instruction naming its own picture:", f"{sum(1 for one in named if one)} of 4", named)
    print(
        "  a picture named by another's instruction:",
        sum(1 for place in range(4) if pictures[place] >= 0 and names_other(answers[place], pictures[place])),
        "of 4",
    )

    page.click("#go")
    wait_idle(page)
    sent = requests_of(posts)
    # The words in the box lead every image and that image's row joins them, which is how a
    # marked run's rows are composed with the box's words too.
    check(
        "each image is sent the words in the box leading its own instruction",
        [sent.get(str(place + 1)) for place in range(4)] == [f"{KEEPING_WORDS}. {answer}" for answer in answers],
        f"{[text[:50] for text in sent.values()]}",
    )
    claims = write_results(bodies, OUT)
    check(
        "each result names its own reference, and no two name the same",
        sorted(claims) == ["0", "1", "2", "3"],
        f"references {claims}",
    )

    # The engine obeyed the instruction: each result kept its own picture's scene, so its
    # background is nearer to that picture than to any of the other three.
    rings = [ring(f"{OUT}source-{number}.png") for number in range(1, 5)]
    kept = []
    distances = []
    for place, source in enumerate(pictures):
        result = ring(f"{OUT}out-ref{place}.png")
        nearest, apart = nearest_source(result, rings)
        kept.append(nearest == source)
        distances.append(f"place {place + 1} is source {source + 1}, nearest {nearest + 1}: {apart}")
    check(
        "every result kept the scene of the picture it was written from",
        all(kept),
        "; ".join(distances),
    )
    check("no console errors", not errors, "; ".join(errors))

    browser.close()

failed = [name for name, passed in results if not passed]
print(f"\n{len(results) - len(failed)}/{len(results)} passed", "FAILED: " + ", ".join(failed) if failed else "")
sys.exit(1 if failed else 0)
