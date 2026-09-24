from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway


class CancelRunUseCase:
    """Stop the run in flight at the end of its step, and the rest of its batch."""

    def __init__(self, progress: ProgressGateway):
        self._progress = progress

    def execute(self) -> None:
        self._progress.request_cancel()
