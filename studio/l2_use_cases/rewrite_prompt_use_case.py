"""Lengthen what is in the prompt box, and free the image engines while it runs.

The rewriter is a second model and it does not fit beside an image engine on a
64 GB machine, so the engines go first and the run that follows loads one back.
That is the rule the qwen21 backend already applies to its own two engines, one
level up: never hold two models. The cost is one engine rebuild after a rewrite,
3.8s for mflux.

This use case also publishes the rewrite's phase, because the page draws its
button from it: a rewrite is worth cancelling, and the page can only offer that
while the model is writing rather than loading.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from studio.l1_entities.capabilities import Capabilities
from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.image_job import ReferenceImage
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.boundaries.rewrite_progress_gateway import RewriteProgressGateway

# A rewriter suggests a shape as a ratio, and only a generate mode offers one:
# its size choices are named "WxH". An edit mode sizes itself from the picture
# it is given, so a ratio from the rewriter changes nothing there.
_RATIO_TOLERANCE = 0.01


class Clock(Protocol):
    def __call__(self) -> float: ...


@dataclass(frozen=True)
class RewriteRequest:
    prompt: str
    mode: str
    references: tuple[ReferenceImage, ...] = ()


@dataclass(frozen=True)
class RewriteResponse:
    prompt: str
    size: str | None
    """A size choice of the mode, or None when the rewriter suggested no shape."""
    elapsed: float
    cancelled: bool = False
    """True when the page stopped the rewrite. The prompt is then the one it sent."""


def _shapes(capabilities: Capabilities, mode_id: str) -> tuple[tuple[str, float], ...]:
    """The mode's size choices that name a width and a height, with their ratios."""
    found = []
    for param in capabilities.mode(mode_id).params:
        if param.kind != "choice":
            continue
        for choice in param.choices:
            width, _, height = choice.value.partition("x")
            if width.isdigit() and height.isdigit():
                found.append((choice.value, int(width) / int(height)))
    return tuple(found)


def _size_for(ratio: str, capabilities: Capabilities, mode_id: str) -> str | None:
    """The declared size whose shape is closest to `ratio`, within one percent.

    Within one percent, because the list is on a 16 pixel grid and no ratio lands
    exactly. Outside it the rewriter asked for a shape this mode cannot render,
    and saying nothing is better than silently rendering a different one.
    """
    left, _, right = ratio.partition(":")
    if not (left.isdigit() and right.isdigit() and int(right)):
        return None
    wanted = int(left) / int(right)
    close = [(abs(value - wanted) / wanted, name) for name, value in _shapes(capabilities, mode_id)]
    if not close:
        return None
    off, name = min(close)
    return name if off <= _RATIO_TOLERANCE else None


class RewritePromptUseCase:
    def __init__(
        self,
        rewriter: PromptRewriterGateway,
        catalog: BackendCatalogGateway,
        progress: RewriteProgressGateway,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._rewriter = rewriter
        self._catalog = catalog
        self._progress = progress
        self._clock = clock

    def execute(self, request: RewriteRequest) -> RewriteResponse:
        if not request.prompt.strip():
            raise InvalidJob("Write something to rewrite first.")
        if request.mode not in self._rewriter.modes():
            raise InvalidJob(f"This backend rewrites no {request.mode} prompt.")
        started = self._clock()
        for backend_id in self._catalog.visible_ids():
            self._catalog.get(backend_id).release()
        # A cancel that arrived when nothing was in flight is stale, and a fresh
        # rewrite must not be born cancelled. The run's use case clears its own the
        # same way, for the same reason.
        self._progress.clear_cancel()
        # The page polls this state for the whole rewrite, so it learns which side
        # of the load it is on: a cold rewriter loads about 19 GB before it writes.
        self._progress.begin()
        try:
            rewrite = self._rewriter.rewrite(
                request.prompt,
                request.mode,
                request.references,
                self._progress.writing,
                self._progress.cancel_requested,
            )
        except Cancelled:
            # The page asked for this, so it is not a failure and it carries no
            # words. The rewriter is the one model the two jobs do not share, so
            # giving its memory back is what the cancel is for, and this is the
            # thread whose loop has just stopped.
            self._rewriter.release()
            return RewriteResponse(prompt=request.prompt, size=None, elapsed=self._clock() - started, cancelled=True)
        finally:
            self._progress.finish()
        capabilities = self._catalog.get(self._catalog.active_id()).capabilities()
        size = _size_for(rewrite.ratio, capabilities, request.mode) if rewrite.ratio else None
        return RewriteResponse(prompt=rewrite.prompt, size=size, elapsed=self._clock() - started)
