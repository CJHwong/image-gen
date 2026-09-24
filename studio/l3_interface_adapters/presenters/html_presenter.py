"""Everything the server sends back is HTML for htmx: the page, and fragments.

The fragments carry data, not layout. The page moves an image into its gallery
and draws the progress card itself.
"""

import base64
import html
import json
from dataclasses import asdict

from studio.l1_entities.errors import Cancelled, InvalidJob, StudioError
from studio.l1_entities.run_progress import RunProgress
from studio.l2_use_cases.describe_studio_use_case import StudioView
from studio.l2_use_cases.run_image_use_case import NextRun, RunImageResponse

ITEM = """<div class="item" data-seed="{seed}" data-width="{width}" data-height="{height}"
  data-steps="{steps}" data-elapsed="{elapsed:.0f}" data-position="{position}"
  data-mode="{mode}" data-prompt="{prompt}"><img src="data:image/png;base64,{b64}" alt=""></div>"""

CHAIN = (
    '<div class="chain" data-progress="{progress}" hx-post="/generate"'
    ' hx-vals=\'{values}\' hx-trigger="load" hx-target="this"'
    ' hx-swap="outerHTML"></div>'
)

# Every progress answer carries the next poller, so the loop clocks itself. The
# page ends it by clearing #progress. The server cannot end it: between two
# images of a batch, and between the click and the run starting, nothing runs
# but more is coming, and ending there killed the poller for the whole run.
POLLER = '<div hx-get="/progress" hx-trigger="load delay:800ms" hx-target="#progress" hx-swap="innerHTML"></div>'


class HtmlPresenter:
    def __init__(self, page_template: str):
        self._page = page_template

    def page(self, view: StudioView) -> str:
        active = view.active
        studio = {
            "backend": {
                "id": active.backend_id,
                "name": active.name,
                "badge": active.badge,
                "max_batch": active.max_batch,
            },
            "backends": [list(backend) for backend in view.backends],
            "modes": [asdict(mode) for mode in active.modes],
        }
        # The JSON sits in a script tag, where "</" would end the tag early.
        data = json.dumps(studio, ensure_ascii=False).replace("</", "<\\/")
        return (
            self._page.replace("__NAME__", html.escape(active.name))
            .replace("__BACKEND__", html.escape(active.backend_id))
            .replace("__BADGE__", html.escape(active.badge))
            .replace("__STUDIO__", data)
        )

    def run(self, response: RunImageResponse) -> str:
        image = response.image
        item = ITEM.format(
            b64=base64.b64encode(image.png).decode("ascii"),
            position=response.position,
            seed=image.seed,
            width=image.width,
            height=image.height,
            steps=image.steps,
            elapsed=response.elapsed,
            prompt=html.escape(response.prompt, quote=True),
            mode=response.mode,
        )
        return item + (self._chain(response.next_run) if response.next_run else "")

    @staticmethod
    def _chain(next_run: NextRun) -> str:
        """The placeholder that fetches the next image of the batch.

        It carries every text value it needs. The reference images are the one
        exception: they stay on the server under the token, so a large image is
        not posted again for each image.
        """
        values = {
            **next_run.options,
            "mode": next_run.mode,
            "prompt": next_run.prompt,
            "seed": str(next_run.seed),
            "total": str(next_run.total),
            "index": str(next_run.index),
            "reference_token": next_run.reference_token,
            "backend": next_run.backend,
        }
        return CHAIN.format(
            progress=f"{next_run.index} of {next_run.total}", values=html.escape(json.dumps(values), quote=True)
        )

    @staticmethod
    def failure(error: Exception) -> str:
        if isinstance(error, Cancelled):
            return f'<div class="hint">Cancelled ({html.escape(str(error))}).</div>'
        if isinstance(error, InvalidJob):
            message = f"Bad form value: {error}"
        elif isinstance(error, StudioError):
            message = str(error)
        else:
            message = f"{type(error).__name__}: {error}"
        return f'<div class="err">{html.escape(message)}</div>'

    @staticmethod
    def progress(state: RunProgress) -> str:
        if not state.running:
            return POLLER
        return (
            f'<div class="progress-state" data-stage="{state.stage}"'
            f' data-step="{state.step}" data-total="{state.total}"'
            f' data-label="{html.escape(state.label, quote=True)}"'
            f' data-stopping="{1 if state.stopping else 0}"></div>{POLLER}'
        )
