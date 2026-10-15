import threading

import pytest

from studio.l1_entities.errors import BackendBusy
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l2_use_cases.run_video_use_case import RunVideoUseCase


class FakeVideoBackend(VideoBackendGateway):
    def __init__(self, failure=None):
        self.failure = failure
        self.jobs = []

    def run(self, job: VideoJob) -> VideoResult:
        self.jobs.append(job)
        if self.failure:
            raise self.failure
        return VideoResult(b"mp4", job.width, job.height, job.num_frames, job.frame_rate, job.seed)


def job():
    return VideoJob("moving clouds", 960, 544, 145, 24, 7)


def test_video_run_calls_its_backend_and_releases_the_shared_lock():
    backend = FakeVideoBackend()
    lock = threading.Lock()
    use_case = RunVideoUseCase(backend, lock)

    response = use_case.execute(job())

    assert backend.jobs == [job()]
    assert response.mp4 == b"mp4"
    assert lock.acquire(blocking=False)
    lock.release()


def test_video_run_refuses_to_queue_behind_an_image_run():
    backend = FakeVideoBackend()
    lock = threading.Lock()
    lock.acquire()
    use_case = RunVideoUseCase(backend, lock)

    with pytest.raises(BackendBusy, match="busy with a run"):
        use_case.execute(job())

    assert backend.jobs == []
    lock.release()


def test_video_run_releases_the_lock_when_the_pipeline_fails():
    backend = FakeVideoBackend(RuntimeError("pipeline failed"))
    lock = threading.Lock()
    use_case = RunVideoUseCase(backend, lock)

    with pytest.raises(RuntimeError, match="pipeline failed"):
        use_case.execute(job())

    assert lock.acquire(blocking=False)
    lock.release()
