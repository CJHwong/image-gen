"""Run speech in the studio's shared memory slot."""

import threading
from dataclasses import replace

from studio.l1_entities.errors import BackendBusy, BackendChanged, Cancelled
from studio.l1_entities.voice_job import SpeechJob, SpeechResult
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway
from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway
from studio.l2_use_cases.boundaries.voice_backend_catalog_gateway import VoiceBackendCatalogGateway
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway


class RunVoiceUseCase:
    def __init__(
        self,
        backend: VoiceBackendGateway,
        progress: ProgressGateway,
        engine_lock: threading.Lock,
        residency: ModelResidencyGateway,
        catalog: VoiceBackendCatalogGateway | None = None,
    ):
        self._backend = backend
        self._progress = progress
        self._engine_lock = engine_lock
        self._residency = residency
        self._catalog = catalog

    def execute(self, job: SpeechJob, backend_id: str = "auk") -> SpeechResult:
        return self.execute_batch([job], lambda index, result: None, lambda index, total: None, backend_id)[0]

    def execute_batch(self, jobs, completed, started, backend_id="auk"):
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("The model is busy. Wait for it, or cancel the active operation.")
        try:
            if self._catalog is not None and backend_id != self._catalog.active_id():
                raise BackendChanged("The Voice model changed in another tab. Reload the page.")
            if self._catalog is not None:
                self._backend = self._catalog.get(backend_id)
            self._progress.clear_cancel()
            self._progress.begin("", kind="voice")
            self._residency.activate(backend_id)
            return self._run_loaded(jobs, completed, started)
        finally:
            self._progress.finish()
            self._engine_lock.release()

    def _run_loaded(self, jobs, completed, started):
        finished = threading.Event()
        watcher = threading.Thread(target=self._watch_loading, args=(finished,), daemon=True)
        watcher.start()
        try:
            self._backend.load()
            self._backend.prepare_batch(jobs, self._progress.cancel_requested)
            return self._make_takes(jobs, completed, started)
        except Exception:
            if self._progress.cancel_requested():
                raise Cancelled("Voice generation was cancelled.") from None
            raise
        finally:
            finished.set()
            watcher.join()

    def _make_takes(self, jobs, completed, started):
        results = []
        for index, job in enumerate(jobs, start=1):
            if self._progress.cancel_requested():
                raise Cancelled("Voice generation was cancelled.")
            self._progress.begin("", kind="voice")
            started(index, len(jobs))
            result = self._backend.run(job, self._progress.set_step, self._progress.cancel_requested)
            result = replace(result, text=job.text)
            completed(index, result)
            results.append(result)
        return results

    def _watch_loading(self, finished: threading.Event) -> None:
        while not finished.wait(0.1):
            if self._progress.cancel_requested():
                self._backend.release()
                return
