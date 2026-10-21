import threading

import pytest

from studio.l1_entities.errors import BackendBusy, BackendChanged, Cancelled
from studio.l1_entities.run_progress import RunProgress
from studio.l1_entities.video_job import VideoJob
from studio.l2_use_cases.run_video_use_case import RunVideoUseCase
from studio.l3_interface_adapters.gateways.in_memory_model_residency_gateway import (
    InMemoryModelResidencyGateway,
)
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway
from studio.l3_interface_adapters.gateways.in_memory_video_backend_catalog_gateway import (
    InMemoryVideoBackendCatalogGateway,
)
from tests.support.fakes import FakeBackendGateway, FakeVideoBackendGateway


def job():
    return VideoJob("moving clouds", 960, 544, 145, 24, 7)


def test_batch_publishes_cancellable_preparation_before_the_first_clip(monkeypatch):
    use_case, _, _, video, progress, _, lock = setup()
    events = []

    def preparing(jobs, completed, started, report, cancelled):
        assert progress.snapshot() == RunProgress(
            running=True, stage="preparing", label="Preparing clips", kind="video", request_id="batch-a"
        )
        assert lock.locked()
        assert use_case.cancel("batch-a")
        assert cancelled()
        raise Cancelled("cancelled during preparation")

    monkeypatch.setattr(video, "run_batch", preparing)
    with pytest.raises(Cancelled, match="cancelled"):
        use_case.execute_batch(
            [job(), job()], "video-fake", "batch-a", events.append, lambda *args: events.append(args), lambda: False
        )
    assert events == []
    assert progress.snapshot() == RunProgress()
    assert not progress.cancel_requested()
    assert not lock.locked()


def test_batch_keeps_one_model_and_lock_until_every_item_finishes():
    use_case, _, image, video, progress, residency, lock = setup()
    events = []

    def started(index, total):
        assert lock.locked()
        events.append(("started", index, total))

    def completed(index, result):
        assert lock.locked()
        events.append(("completed", index, result.seed))

    results = use_case.execute_batch([job(), job()], "video-fake", "batch-a", completed, started, lambda: False)
    assert len(results) == 2
    assert events == [("started", 1, 2), ("completed", 1, 7), ("started", 2, 2), ("completed", 2, 7)]
    assert video.jobs == [job(), job()]
    assert image.events == ["release"]
    assert residency.active_id() == "video-fake"
    assert progress.snapshot() == RunProgress()
    assert not lock.locked()


def test_batch_cancel_between_items_keeps_first_output_and_releases_lock():
    use_case, _, _, video, progress, _, lock = setup()
    completed = []
    with pytest.raises(Cancelled):
        use_case.execute_batch(
            [job(), job()],
            "video-fake",
            "batch-a",
            lambda index, result: completed.append(result),
            lambda index, total: None,
            lambda: bool(completed),
        )
    assert len(completed) == 1
    assert len(video.jobs) == 1
    assert not lock.locked()
    assert progress.snapshot() == RunProgress()


def test_batch_refuses_a_busy_engine():
    use_case, _, _, _, _, _, lock = setup()
    lock.acquire()
    with pytest.raises(BackendBusy):
        use_case.execute_batch(
            [job()], "video-fake", "batch-a", lambda index, result: None, lambda index, total: None, lambda: False
        )
    lock.release()


def test_batch_refuses_a_changed_backend():
    use_case, catalog, _, _, _, _, lock = setup()
    catalog.set_active("other-video")
    with pytest.raises(BackendChanged):
        use_case.execute_batch(
            [job()], "video-fake", "batch-a", lambda index, result: None, lambda index, total: None, lambda: False
        )
    assert not lock.locked()


def test_batch_engine_failure_releases_lock_and_progress():
    use_case, _, _, _, progress, _, lock = setup(RuntimeError("engine failed"))
    with pytest.raises(RuntimeError, match="engine failed"):
        use_case.execute_batch(
            [job()], "video-fake", "batch-a", lambda index, result: None, lambda index, total: None, lambda: False
        )
    assert not lock.locked()
    assert progress.snapshot() == RunProgress()


def test_batch_reports_cancellation_when_it_causes_an_engine_failure():
    use_case, _, _, _, progress, _, lock = setup(RuntimeError("child stopped"))

    def started(index, total):
        progress.request_cancel("batch-a")

    with pytest.raises(Cancelled, match="cancelled"):
        use_case.execute_batch([job()], "video-fake", "batch-a", lambda index, result: None, started, lambda: False)
    assert not lock.locked()
    assert not progress.cancel_requested()


def test_batch_reports_external_cancellation_when_it_causes_an_engine_failure():
    use_case, _, _, _, progress, _, lock = setup(RuntimeError("child stopped"))
    stopping = []

    def started(index, total):
        stopping.append(True)

    with pytest.raises(Cancelled, match="cancelled"):
        use_case.execute_batch(
            [job()], "video-fake", "batch-a", lambda index, result: None, started, lambda: bool(stopping)
        )
    assert not lock.locked()
    assert not progress.cancel_requested()


def setup(failure=None, progress=None):
    image = FakeBackendGateway()
    video = FakeVideoBackendGateway(failure=failure)
    other_video = FakeVideoBackendGateway("other-video", "Other video")
    video_backends = {"video-fake": video, "other-video": other_video}
    catalog = InMemoryVideoBackendCatalogGateway(video_backends, "video-fake", tuple(video_backends))
    residency = InMemoryModelResidencyGateway({"fake": image, **video_backends})
    residency.activate("fake")
    engine_lock = threading.Lock()
    progress = progress or InMemoryProgressGateway()
    use_case = RunVideoUseCase(catalog, progress, engine_lock, residency)
    return use_case, catalog, image, video, progress, residency, engine_lock


def test_video_run_releases_the_image_model_before_running_video():
    use_case, _, image, video, progress, residency, engine_lock = setup()

    response = use_case.execute(job(), "video-fake", "run-a")

    assert image.events == ["release"]
    assert video.jobs == [job()]
    assert response.mp4 == b"mp4"
    assert residency.active_id() == "video-fake"
    assert progress.snapshot() == RunProgress()
    assert engine_lock.acquire(blocking=False)
    engine_lock.release()


def test_video_run_reports_prepare_and_model_steps():
    observed = []

    class RecordingProgressGateway(InMemoryProgressGateway):
        def begin(self, label, kind="image", request_id=None):
            super().begin(label, kind, request_id)
            observed.append(self.snapshot())

        def set_step(self, step, total, phase=0):
            super().set_step(step, total, phase)
            observed.append(self.snapshot())

        def finish(self):
            super().finish()
            observed.append(self.snapshot())

    progress = RecordingProgressGateway()
    use_case, _, _, _, _, _, _ = setup(progress=progress)

    use_case.execute(job(), "video-fake", "run-a")

    assert observed == [
        RunProgress(running=True, stage="preparing", kind="video", request_id="run-a"),
        RunProgress(running=True, stage="running", step=4, total=8, kind="video", phase=1, request_id="run-a"),
        RunProgress(),
    ]


def test_video_run_refuses_to_queue_behind_an_image_run():
    use_case, _, _, video, _, residency, engine_lock = setup()
    engine_lock.acquire()

    with pytest.raises(BackendBusy, match="busy with a run"):
        use_case.execute(job(), "video-fake", "run-a")

    assert video.jobs == []
    assert residency.active_id() == "fake"
    engine_lock.release()


def test_video_run_rejects_a_model_changed_in_another_tab():
    use_case, catalog, _, video, _, residency, _ = setup()
    catalog.set_active("other-video")

    with pytest.raises(BackendChanged, match="video model changed"):
        use_case.execute(job(), "video-fake", "run-a")

    assert video.jobs == []
    assert residency.active_id() == "fake"


def test_video_run_releases_the_lock_when_the_pipeline_fails():
    use_case, _, _, video, progress, _, engine_lock = setup(RuntimeError("pipeline failed"))

    with pytest.raises(RuntimeError, match="pipeline failed"):
        use_case.execute(job(), "video-fake", "run-a")

    assert video.jobs == [job()]
    assert progress.snapshot() == RunProgress()
    assert engine_lock.acquire(blocking=False)
    engine_lock.release()


def test_video_run_passes_cancellation_to_the_backend_and_clears_the_flag():
    progress_state = InMemoryProgressGateway()

    class CancellableVideo(FakeVideoBackendGateway):
        def run(self, job, progress=None, cancelled=None):
            assert cancelled is not None
            progress_state.request_cancel("run-a")
            assert cancelled()
            raise Cancelled("video generation was cancelled")

    image = FakeBackendGateway()
    video = CancellableVideo()
    catalog = InMemoryVideoBackendCatalogGateway({"video-fake": video}, "video-fake", ("video-fake",))
    residency = InMemoryModelResidencyGateway({"fake": image, "video-fake": video})
    use_case = RunVideoUseCase(catalog, progress_state, threading.Lock(), residency)

    with pytest.raises(Cancelled, match="video generation was cancelled"):
        use_case.execute(job(), "video-fake", "run-a")

    assert not progress_state.cancel_requested()
    assert not progress_state.snapshot().running


def test_video_run_converts_a_child_failure_after_cancel_to_cancelled():
    progress_state = InMemoryProgressGateway()

    class CancelledVideo(FakeVideoBackendGateway):
        def run(self, job, progress=None, cancelled=None):
            progress_state.request_cancel("run-a")
            raise RuntimeError("child stopped")

    image = FakeBackendGateway()
    video = CancelledVideo()
    catalog = InMemoryVideoBackendCatalogGateway({"video-fake": video}, "video-fake", ("video-fake",))
    residency = InMemoryModelResidencyGateway({"fake": image, "video-fake": video})
    use_case = RunVideoUseCase(catalog, progress_state, threading.Lock(), residency)

    with pytest.raises(Cancelled, match="video generation was cancelled"):
        use_case.execute(job(), "video-fake", "run-a")

    assert not progress_state.cancel_requested()
    assert not progress_state.snapshot().running


def test_video_cancel_only_matches_the_active_request_id():
    use_case, _, _, _, progress, _, _ = setup()
    progress.begin("", kind="video", request_id="run-a")

    assert use_case.cancel("run-b") is False
    assert progress.cancel_requested() is False
    assert use_case.cancel("run-a") is True
    assert progress.cancel_requested() is True
