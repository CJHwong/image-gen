"""Stop the rewrite in flight.

The rewriter checks the cancel flag before its first segment and between segments,
so a stop is always observed. The use case that owns the rewrite frees the rewriter
after its loop has stopped, so nothing here has to reach into another thread, and
there is no escalation to run.
"""

from studio.l2_use_cases.boundaries.rewrite_progress_gateway import RewriteProgressGateway


class CancelRewriteUseCase:
    """Stop the rewrite in flight."""

    def __init__(self, progress: RewriteProgressGateway):
        self._progress = progress

    def execute(self) -> None:
        self._progress.request_cancel()
