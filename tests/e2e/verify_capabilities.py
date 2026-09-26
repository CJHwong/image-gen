"""Real-run check that the page follows the backend's capabilities.

It serves the real page and routes on two backends that make no model call:
one with the qwen21 capabilities, and one with a generate mode only, a steps
param only, no Looks and no templates. It needs no GPU and runs in seconds.

Usage: uv run --with playwright python tests/e2e/verify_capabilities.py
"""

import io
import re
import sys
import threading
from http.server import ThreadingHTTPServer

from PIL import Image
from playwright.sync_api import sync_playwright

from studio.l1_entities.capabilities import Capabilities, ModeSpec, ParamSpec
from studio.l1_entities.image_job import ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.prompt_aids import EDIT_TEMPLATES
from studio.l3_interface_adapters.gateways.qwen21.capabilities import qwen21_capabilities
from studio.l4_frameworks_and_drivers.main import assemble_studio

TINY = Capabilities(
    backend_id="tiny",
    name="Tiny",
    badge="int4",
    max_batch=2,
    modes=(
        ModeSpec(
            id="generate",
            label="Draw",
            params=(ParamSpec(id="steps", kind="number", default=5, minimum=1, maximum=9, integer=True, step=1),),
            prompt_hint="Tiny prompt hint",
        ),
    ),
)

# A backend that takes one picture and shares qwen21's edit templates, but does not
# declare a region. The page has to keep the draw tool, and the one template whose
# whole point is a mask, away from it, and offer the rest.
PLAIN = Capabilities(
    backend_id="plain",
    name="Plain",
    badge="fp16",
    max_batch=1,
    modes=(
        ModeSpec(
            id="generate",
            label="Draw",
            params=(ParamSpec(id="steps", kind="number", default=6, minimum=1, maximum=9, integer=True, step=1),),
            prompt_hint="Plain prompt hint",
        ),
        ModeSpec(
            id="edit",
            label="Touch up",
            params=(ParamSpec(id="steps", kind="number", default=6, minimum=1, maximum=9, integer=True, step=1),),
            min_references=1,
            max_references=2,
            templates=EDIT_TEMPLATES,
            prompt_hint="Plain edit hint",
        ),
    ),
)


class StubBackendGateway(ImageBackendGateway):
    def __init__(self, capabilities):
        self.caps = capabilities
        self.jobs = []

    def capabilities(self):
        return self.caps

    def load(self):
        pass

    def run(self, job, on_step, should_stop):
        self.jobs.append(job)
        buffer = io.BytesIO()
        Image.new("RGB", (64, 64), "teal").save(buffer, format="PNG")
        return ImageResult(png=buffer.getvalue(), width=64, height=64, seed=job.seed, steps=job.options["steps"])

    def release(self):
        pass


TIMES = "\u00d7"  # the sign the page prints between width and height
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))


def visible(page, selector):
    return page.locator(selector).first.is_visible()


def seconds(text):
    """The seconds in an estimate such as "about 2 min 45s"."""
    minutes = re.search(r"(\d+) min", text)
    rest = re.search(r"(\d+)s", text)
    return (int(minutes.group(1)) * 60 if minutes else 0) + (int(rest.group(1)) if rest else 0)


def main():
    qwen = StubBackendGateway(qwen21_capabilities("bf16"))
    tiny, plain = StubBackendGateway(TINY), StubBackendGateway(PLAIN)
    studio = assemble_studio({"qwen21": qwen, "tiny": tiny, "plain": plain}, "qwen21", ("qwen21", "tiny", "plain"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    errors = []
    with sync_playwright() as playwright:
        page = playwright.chromium.launch().new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: dialog.accept())  # the switch warns about the stub run's image
        page.goto(url)
        check("the title is a switch with three backends", not page.is_disabled("#backend-toggle"))
        check("the qwen21 page has both modes", not page.is_disabled("#mode-edit"))
        page.click("#advanced summary")
        check("guidance shows in generate", visible(page, "#guidance"))
        check("steps start at the spec default", page.input_value("#steps") == "40", page.input_value("#steps"))
        check("guidance is a slider", page.get_attribute("#guidance", "type") == "range")

        page.fill("#prompt", "a lighthouse")
        before = page.inner_text("#go-sub")
        page.fill("#negative", "blur")
        check(
            "a negative prompt raises guidance to what the spec names",
            page.input_value("#guidance") == "2.5",
            page.input_value("#guidance"),
        )
        check(
            "a note says why and what it costs",
            visible(page, "#negative-note") and "twice" in page.inner_text("#negative-note"),
            page.inner_text("#negative-note"),
        )
        after = page.inner_text("#go-sub")
        check("the estimate counts the second pass", seconds(after) >= 1.8 * seconds(before), f"{before} -> {after}")
        page.fill("#negative", "")
        check("clearing it puts guidance back", page.input_value("#guidance") == "1", page.input_value("#guidance"))
        page.fill("#negative", "blur")
        page.evaluate(
            "const g = document.getElementById('guidance'); g.value = 4;"
            " g.dispatchEvent(new Event('input', { bubbles: true }))"
        )
        page.fill("#negative", "")
        check("a guidance set by hand stays", page.input_value("#guidance") == "4", page.input_value("#guidance"))
        blank = page.inner_text("#go-sub")
        check("guidance without a negative runs one pass", seconds(blank) == seconds(before), f"{before} -> {blank}")
        page.fill("#prompt", "")

        check("no Clear without a seed", not visible(page, "#clear-seed"))
        page.fill("#seed", "7")
        check("Clear shows with a seed", visible(page, "#clear-seed"))
        page.click("#clear-seed")
        check("Clear empties the seed", page.input_value("#seed") == "" and not visible(page, "#clear-seed"))

        tiers = page.locator("#tier-sizes button").all_inner_texts()
        check("tiers are labeled by megapixels", tiers == ["0.3 MP", "0.6 MP", "1 MP", "1.8 MP"], str(tiers))
        check(
            "the pixel size shows once",
            page.inner_text("#size-caption") == f"1024 {TIMES} 1024" and not any(TIMES in tier for tier in tiers),
            page.inner_text("#size-caption"),
        )

        page.click("#look summary")
        rows = page.locator("#look-rows .look-row-toggle")
        check(
            "Look rows start closed",
            rows.count() == 8 and page.locator("#look-rows .chip:visible").count() == 0,
            str(rows.count()),
        )
        rows.filter(has_text="Light").click()
        open_chips = page.locator("#look-rows .chip:visible").all_inner_texts()
        check(
            "a row opens only its own chips",
            open_chips[:1] == ["Soft window light"] and len(open_chips) == 5,
            str(open_chips),
        )
        light_top = rows.filter(has_text="Light").bounding_box()["y"]
        page.locator("#look-rows .chip", has_text="Overcast").click()
        moved = rows.filter(has_text="Light").bounding_box()["y"] - light_top
        check("a pick keeps its row under the pointer", abs(moved) <= 1, f"moved {moved:.0f}px")
        check(
            "a pick closes the row and shows in it",
            page.locator("#look-rows .chip:visible").count() == 0
            and "Overcast" in rows.filter(has_text="Light").inner_text(),
        )
        height = round(page.locator("#look").bounding_box()["height"])
        check("closed rows keep Look short", height < 400, f"{height}px for 8 rows")
        tail = page.locator("#look-adds")
        prompt_box = page.locator("#prompt").bounding_box()
        tail_box = tail.bounding_box()
        check(
            "the Look text sits right under the prompt",
            visible(page, "#look-adds") and 0 <= tail_box["y"] - (prompt_box["y"] + prompt_box["height"]) < 20,
            str(tail_box),
        )
        check(
            "it names the pick and quotes the sentence",
            tail.locator(".chip").all_inner_texts() == ["Overcast \u00d7"] and len(tail.locator("q").inner_text()) > 10,
            tail.inner_text(),
        )
        tail.locator(".chip").click()
        check(
            "its chip unpicks",
            not visible(page, "#look-adds") and "none" in rows.filter(has_text="Light").inner_text(),
        )
        page.evaluate(
            "const g = document.getElementById('guidance'); g.value = 1;"
            " g.dispatchEvent(new Event('input', { bubbles: true }))"
        )
        rows.filter(has_text="Realism").click()
        page.locator("#look-rows .chip", has_text="Real person").click()
        check(
            "Real person raises guidance for its avoid part",
            page.input_value("#guidance") == "2.5" and "airbrushed skin" in tail.locator(".look-avoids").inner_text(),
            f"{page.input_value('#guidance')}, {tail.inner_text()!r}",
        )
        check(
            "the negative field shows what the Look adds",
            page.input_value("#negative") == "" and "airbrushed skin" in page.inner_text("#negative-look"),
            page.inner_text("#negative-look"),
        )
        tail.locator(".chip").click()
        check("unpicking it clears that line", not visible(page, "#negative-look"))
        check("unpicking it puts guidance back", page.input_value("#guidance") == "1", page.input_value("#guidance"))

        page.click("label[for=mode-edit]")
        check("guidance hides in edit", not visible(page, "#guidance"))
        check("edit guidance starts at the spec default", page.input_value("#cfg") == "1", page.input_value("#cfg"))
        check(
            "edit calls its scale Guidance too",
            page.inner_text("label[for=cfg]") == "Guidance" and page.get_attribute("#cfg", "type") == "range",
        )
        check(
            "the edit summary says guidance",
            "guidance" in (page.text_content("#advanced-values") or ""),
            page.text_content("#advanced-values"),
        )
        edits = page.locator("#edit-sizes button").all_inner_texts()
        check("edit sizes use the same labels", edits == ["Match", "0.3 MP", "0.6 MP", "1 MP", "1.8 MP"], str(edits))
        page.click("label[for=mode-generate]")

        rows.filter(has_text="Light").click()
        page.locator("#look-rows .chip", has_text="Overcast").click()
        rows.filter(has_text="Realism").click()
        page.locator("#look-rows .chip", has_text="Real person").click()
        page.fill("#prompt", "a lighthouse")
        page.fill("#negative", "blur")
        page.click("#go")
        page.wait_for_function("document.querySelectorAll('#strip .frame:not(.pending)').length === 1")
        sent = qwen.jobs[-1]
        check(
            "the model gets the Look after the prompt",
            sent.prompt.startswith("a lighthouse. Overcast sky") and "An everyday photo" in sent.prompt,
            sent.prompt,
        )
        check(
            "the negative is the typed one, then the Look's avoid part",
            sent.options["negative"].startswith("blur, beauty filter") and sent.options["guidance"] == 2.5,
            f"{sent.options['negative']!r}, {sent.options['guidance']}",
        )
        check(
            "the caption shows what the model got, the Look muted",
            page.inner_text(".prompt-line") == sent.prompt
            and page.inner_text(".prompt-line .look-said").startswith("Overcast sky"),
            f"{page.inner_text('.prompt-line')!r} vs {sent.prompt!r}",
        )
        # A run takes everything the form held, so the prompt, the Look and the
        # negative are already gone here, and there is nothing to unpick.
        check(
            "a run empties the form it sent",
            page.input_value("#prompt") == ""
            and page.input_value("#negative") == ""
            and tail.locator(".chip").count() == 0
            and tail.is_hidden(),
            f"{page.input_value('#prompt')!r}, {tail.inner_text()!r}, {page.input_value('#negative')!r}",
        )
        page.get_by_role("button", name="More actions").click()
        page.get_by_role("menuitem", name="Reuse prompt").click()
        check(
            "Reuse prompt brings back the text, the Look and the negative",
            page.input_value("#prompt") == "a lighthouse"
            and tail.locator(".chip").all_inner_texts() == [f"Overcast {TIMES}", f"Real person {TIMES}"]
            and page.input_value("#negative") == "blur",
            f"{page.input_value('#prompt')!r}, {tail.inner_text()!r}, {page.input_value('#negative')!r}",
        )
        page.click("label[for=mode-edit]")
        page.get_by_role("button", name="More actions").click()
        page.get_by_role("menuitem", name="Reuse prompt").click()
        check(
            "in a mode without that Look, Reuse prompt brings it back as text",
            page.input_value("#prompt") == sent.prompt and not visible(page, "#look-adds"),
            page.input_value("#prompt"),
        )
        page.click("label[for=mode-generate]")

        page.click("#backend-toggle")
        check(
            "the menu marks the current model",
            page.locator("#backend-menu [aria-checked=true]").inner_text() == "Qwen-Image-2.1",
        )
        page.get_by_role("menuitemradio", name="Tiny").click()
        page.wait_for_function("STUDIO.backend.id === 'tiny'")
        check("a switch reloads on the new backend", page.inner_text("h1") == "Tiny", page.inner_text("h1"))
        check("the caret stays with three backends", page.locator("#backend-toggle .icon").is_visible())
        check("an undeclared mode is disabled", page.is_disabled("#mode-edit"))
        check("the mode takes its label from the spec", page.inner_text("label[for=mode-generate]").strip() == "Draw")
        check("the badge comes from the backend", page.inner_text(".badge") == "int4")
        check("the prompt hint comes from the spec", page.get_attribute("#prompt", "placeholder") == "Tiny prompt hint")
        check("no templates button without templates", not visible(page, "#templates-toggle"))
        check("no Look without Looks", not visible(page, "#look"))
        check("no size field without a size param", not visible(page, "#size-field"))
        if page.get_attribute("#advanced", "open") is None:
            page.click("#advanced summary")
        check("steps show", visible(page, "#steps"))
        check("guidance hides", not visible(page, "#guidance"))
        check("the negative prompt hides", not visible(page, "#negative"))
        check(
            "steps take the spec range",
            page.get_attribute("#steps", "max") == "9" and page.input_value("#steps") == "5",
            page.input_value("#steps"),
        )
        check(
            "no time estimate without an estimate",
            "about" not in page.inner_text("#go-sub"),
            page.inner_text("#go-sub"),
        )
        page.click("#count-toggle")
        check("the count menu stops at max_batch", page.locator("#count-menu [role=menuitemradio]").count() == 2)
        page.keyboard.press("Escape")
        page.fill("#prompt", "a teal square")
        page.click("#go")
        page.wait_for_function("document.querySelectorAll('#strip .frame:not(.pending)').length === 1")
        check(
            "a run reaches the tiny backend",
            len(tiny.jobs) == 1 and tiny.jobs[0].options == {"steps": 5},
            str(tiny.jobs[0].options if tiny.jobs else None),
        )
        check("the film edge names the backend", "TINY" in page.inner_text(".stage"))

        # A backend that shares the templates and takes one picture, but declares no
        # region: the tool, and the one template whose whole point is a mask, stay
        # away, and the rest of the templates are still offered.
        page.click("#backend-toggle")
        page.get_by_role("menuitemradio", name="Plain").click()
        page.wait_for_function("STUDIO.backend.id === 'plain'")
        check(
            "the plain labels come from its spec",
            page.inner_text("label[for=mode-edit]").strip() == "Touch up",
            page.inner_text("label[for=mode-edit]"),
        )
        page.fill("#prompt", "a plain square")
        page.click("#go")
        page.wait_for_function("document.querySelectorAll('#strip .frame:not(.pending)').length >= 1")
        page.locator("#strip .frame").first.click()
        page.get_by_role("button", name="Edit this", exact=True).click()
        # Wait on the state the tool would need, not on the print: the print is there
        # from the previous view, so asserting as soon as it appears would pass
        # before this view has rendered at all.
        page.wait_for_function(
            "() => references.length === 1 && references[0].source === view && references[0].width > 0"
        )
        check(
            "a mode without region_marking offers no brush, on a frame from its own strip",
            page.locator(".shot .region-mark").count() == 0 and page.locator(".region-tools").count() == 0,
            f"{page.locator('.shot .region-mark').count()} canvases",
        )
        page.get_by_role("button", name="Templates").click()
        names = " ".join(page.locator("#templates [role=menuitem]").all_inner_texts())
        page.keyboard.press("Escape")
        check(
            "and no template that names a region, while the others are offered",
            "Mark a region" not in names and "Change a color or material" in names,
            names[:60],
        )
        check("no page errors", not errors, "; ".join(errors))
    server.shutdown()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
