"""Run one video while sharing the studio's single-model lock."""

import threading

from studio.l1_entities.errors import BackendBusy
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway


class RunVideoUseCase:
    def __init__(self, backend: VideoBackendGateway, engine_lock: "threading.Lock | None" = None):
        self._backend = backend
        self._engine_lock = engine_lock or threading.Lock()

    def execute(self, job: VideoJob) -> VideoResult:
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("The model is busy with a run in another tab. Wait for it, or cancel it there.")
        try:
            return self._backend.run(job)
        finally:
            self._engine_lock.release()
