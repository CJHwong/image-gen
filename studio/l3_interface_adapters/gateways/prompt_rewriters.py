"""The rewriters that hold no model: the routing one, the absent one, and the stub."""

import time
from collections.abc import Callable, Mapping

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway


class NoPromptRewriter(PromptRewriterGateway):
    """A backend with no rewriter. Its empty mode list hides the page's toggle,
    so `rewrite` is reached only by a caller that ignored the list."""

    def modes(self) -> tuple[str, ...]:
        return ()

    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        raise InvalidJob("This backend has no prompt rewriter.")

    def release(self) -> None:
        pass


class CatalogPromptRewriter(PromptRewriterGateway):
    """The rewriter of whichever backend the page is on.

    A rewriter belongs to a backend, and the page may switch backends, so the
    one in force has to follow the catalog. `release` frees every backend's
    rewriter, because the caller asking for memory wants all of it.
    """

    def __init__(self, rewriters: Mapping[str, PromptRewriterGateway], catalog: BackendCatalogGateway):
        self._rewriters = dict(rewriters)
        self._catalog = catalog
        self._none = NoPromptRewriter()

    def modes(self) -> tuple[str, ...]:
        return self._active().modes()

    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        return self._active().rewrite(prompt, mode, references, on_writing, should_stop)

    def release(self) -> None:
        for rewriter in self._rewriters.values():
            rewriter.release()

    def _active(self) -> PromptRewriterGateway:
        return self._rewriters.get(self._catalog.active_id(), self._none)


class StubPromptRewriter(PromptRewriterGateway):
    """The stub's rewriter: the page gets its toggle and its answer, and no model runs.

    It reports every mode the qwen21 rewriter serves, so a change to the page can
    be checked on a machine with no GPU.
    """

    MODES = ("generate", "edit")

    # The stub writes in slices, so a page check can watch both phases and stop the
    # middle of one. The real rewriter loads about 19 GB in the first phase and
    # writes for 22 to 32 seconds in the second, so the shape is the same and only
    # the clock is shorter. The preparing slice is long enough for a poll to see it.
    PREPARING_SECONDS = 1.2
    WRITING_SLICE_SECONDS = 0.6
    WRITING_SLICES = 5

    def modes(self) -> tuple[str, ...]:
        return self.MODES

    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        time.sleep(self.PREPARING_SECONDS)
        # A stop cannot land during the load, here as on the real one. It is
        # remembered instead, and nothing is written after it.
        if should_stop():
            raise Cancelled("stopped while the stub got ready")
        on_writing()
        for _ in range(self.WRITING_SLICES):
            time.sleep(self.WRITING_SLICE_SECONDS)
            if should_stop():
                raise Cancelled("stopped while the stub wrote")
        return PromptRewrite(prompt=f"{prompt} A longer version of it, written for the stub.", ratio="3:2")

    def release(self) -> None:
        pass
