"""Real-run check that the page follows the backend's capabilities.

It serves the real page and routes on two backends that make no model call:
one with the qwen21 capabilities, and one with a generate mode only, a steps
param only, no Looks and no templates. It needs no GPU and runs in seconds.

Usage: uv run --with playwright python tests/e2e/verify_capabilities.py
"""

import io
import sys
import threading
from http.server import ThreadingHTTPServer

from PIL import Image
from playwright.sync_api import sync_playwright

from studio.l1_entities.capabilities import Capabilities, ModeSpec, ParamSpec
from studio.l1_entities.image_job import ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
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


results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))


def visible(page, selector):
    return page.locator(selector).first.is_visible()


def main():
    qwen, tiny = StubBackendGateway(qwen21_capabilities("bf16")), StubBackendGateway(TINY)
    studio = assemble_studio({"qwen21": qwen, "tiny": tiny}, "qwen21", ("qwen21", "tiny"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    errors = []
    with sync_playwright() as playwright:
        page = playwright.chromium.launch().new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        check("the title is a switch with two backends", not page.is_disabled("#backend-toggle"))
        check("the qwen21 page has both modes", not page.is_disabled("#mode-edit"))
        page.click("#advanced summary")
        check("guidance shows in generate", visible(page, "#guidance"))
        check("steps start at the spec default", page.input_value("#steps") == "40", page.input_value("#steps"))
        page.click("label[for=mode-edit]")
        check("guidance hides in edit", not visible(page, "#guidance"))
        page.click("label[for=mode-generate]")

        page.click("#backend-toggle")
        check(
            "the menu marks the current model",
            page.locator("#backend-menu [aria-checked=true]").inner_text() == "Qwen-Image-2.1",
        )
        page.get_by_role("menuitemradio", name="Tiny").click()
        page.wait_for_function("STUDIO.backend.id === 'tiny'")
        check("a switch reloads on the new backend", page.inner_text("h1") == "Tiny", page.inner_text("h1"))
        check("the caret stays with two backends", page.locator("#backend-toggle .icon").is_visible())
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
        check("no page errors", not errors, "; ".join(errors))
    server.shutdown()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
