from studio.l1_entities.rewrite_progress import RewriteProgress
from studio.l2_use_cases.boundaries.rewrite_progress_gateway import RewriteProgressGateway


class ReadRewriteProgressUseCase:
    def __init__(self, progress: RewriteProgressGateway):
        self._progress = progress

    def execute(self) -> RewriteProgress:
        return self._progress.snapshot()
