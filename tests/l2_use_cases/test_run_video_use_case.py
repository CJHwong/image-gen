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
