import threading

import pytest

from studio.l1_entities.errors import BackendBusy, BackendChanged
from studio.l1_entities.video_job import VideoJob
from studio.l2_use_cases.run_video_use_case import RunVideoUseCase
from studio.l3_interface_adapters.gateways.in_memory_model_residency_gateway import (
    InMemoryModelResidencyGateway,
)
from studio.l3_interface_adapters.gateways.in_memory_video_backend_catalog_gateway import (
    InMemoryVideoBackendCatalogGateway,
)
from tests.support.fakes import FakeBackendGateway, FakeVideoBackendGateway


def job():
    return VideoJob("moving clouds", 960, 544, 145, 24, 7)


def setup(failure=None):
    image = FakeBackendGateway()
    video = FakeVideoBackendGateway(failure=failure)
    other_video = FakeVideoBackendGateway("other-video", "Other video")
    video_backends = {"video-fake": video, "other-video": other_video}
    catalog = InMemoryVideoBackendCatalogGateway(video_backends, "video-fake", tuple(video_backends))
    residency = InMemoryModelResidencyGateway({"fake": image, **video_backends})
    residency.activate("fake")
    engine_lock = threading.Lock()
    use_case = RunVideoUseCase(catalog, engine_lock, residency)
    return use_case, catalog, image, video, residency, engine_lock


def test_video_run_releases_the_image_model_before_running_video():
    use_case, _, image, video, residency, engine_lock = setup()

    response = use_case.execute(job(), "video-fake")

    assert image.events == ["release"]
    assert video.jobs == [job()]
    assert response.mp4 == b"mp4"
    assert residency.active_id() == "video-fake"
    assert engine_lock.acquire(blocking=False)
    engine_lock.release()


def test_video_run_refuses_to_queue_behind_an_image_run():
    use_case, _, _, video, residency, engine_lock = setup()
    engine_lock.acquire()

    with pytest.raises(BackendBusy, match="busy with a run"):
        use_case.execute(job(), "video-fake")

    assert video.jobs == []
    assert residency.active_id() == "fake"
    engine_lock.release()


def test_video_run_rejects_a_model_changed_in_another_tab():
    use_case, catalog, _, video, residency, _ = setup()
    catalog.set_active("other-video")

    with pytest.raises(BackendChanged, match="video model changed"):
        use_case.execute(job(), "video-fake")

    assert video.jobs == []
    assert residency.active_id() == "fake"


def test_video_run_releases_the_lock_when_the_pipeline_fails():
    use_case, _, _, video, _, engine_lock = setup(RuntimeError("pipeline failed"))

    with pytest.raises(RuntimeError, match="pipeline failed"):
        use_case.execute(job(), "video-fake")

    assert video.jobs == [job()]
    assert engine_lock.acquire(blocking=False)
    engine_lock.release()
