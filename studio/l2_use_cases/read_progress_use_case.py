from studio.l1_entities.run_progress import RunProgress
from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway


class ReadProgressUseCase:
    def __init__(self, progress: ProgressGateway):
        self._progress = progress

    def execute(self) -> RunProgress:
        return self._progress.snapshot()
