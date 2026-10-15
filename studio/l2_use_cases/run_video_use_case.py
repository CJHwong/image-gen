"""Run one video while sharing the studio's single-model lock."""

import threading

from studio.l1_entities.errors import BackendBusy, BackendChanged
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway
from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway
from studio.l2_use_cases.boundaries.video_backend_catalog_gateway import VideoBackendCatalogGateway
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway


class RunVideoUseCase:
    def __init__(
        self,
        catalog: VideoBackendCatalogGateway,
        progress: ProgressGateway,
        engine_lock: threading.Lock,
        residency: ModelResidencyGateway,
    ):
        self._catalog = catalog
        self._progress = progress
        self._engine_lock = engine_lock
        self._residency = residency

    def execute(self, job: VideoJob, backend_id: str) -> VideoResult:
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("The model is busy with a run in another tab. Wait for it, or cancel it there.")
        try:
            if backend_id != self._catalog.active_id():
                raise BackendChanged("The video model changed in another tab. Reload the page.")
            backend: VideoBackendGateway = self._catalog.get(backend_id)
            self._progress.begin("", kind="video")
            try:
                self._residency.activate(backend_id)
                return backend.run(job, self._progress.set_step)
            finally:
                self._progress.finish()
        finally:
            self._engine_lock.release()
