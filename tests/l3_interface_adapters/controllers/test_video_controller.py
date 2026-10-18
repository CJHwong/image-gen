import base64
import io
import threading
from dataclasses import replace

import pytest
from PIL import Image

from studio.l1_entities.errors import InvalidJob, UnreadableImage
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.run_video_use_case import RunVideoUseCase
from studio.l2_use_cases.switch_video_backend_use_case import SwitchVideoBackendUseCase
from studio.l3_interface_adapters.controllers import video_controller as video_controller_module
from studio.l3_interface_adapters.controllers.video_controller import VideoController, video_job
from studio.l3_interface_adapters.gateways.in_memory_model_residency_gateway import (
    InMemoryModelResidencyGateway,
)
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway
from studio.l3_interface_adapters.gateways.in_memory_video_backend_catalog_gateway import (
    InMemoryVideoBackendCatalogGateway,
)
from tests.support.fakes import FakeVideoBackendGateway, fake_video_capabilities


class UnusedVideoRun(RunVideoUseCase):
    def __init__(self):
        pass

    def execute(self, job: VideoJob, backend_id: str, request_id: str) -> VideoResult:
        pytest.fail("invalid request reached the use case")


def png_data():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), (20, 40, 60)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def transparent_png_data():
    buffer = io.BytesIO()
    Image.new("RGBA", (32, 24), (20, 40, 60, 100)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def payload(**overrides):
    values = {
        "prompt": "A kite rises above the beach",
        "width": 960,
        "height": 544,
        "num_frames": 145,
        "frame_rate": 24,
        "seed": 42,
        "request_id": "run-a",
        "references": [],
    }
    values.update(overrides)
    return values


def build_video_controller(run=None, capabilities=None):
    first = FakeVideoBackendGateway("video-fake", "Fake video", capabilities=capabilities)
    second = FakeVideoBackendGateway("video-other", "Other video")
    backends = {"video-fake": first, "video-other": second}
    catalog = InMemoryVideoBackendCatalogGateway(backends, "video-fake", tuple(backends))
    residency = InMemoryModelResidencyGateway(backends)
    lock = threading.Lock()
    selected_run = run or RunVideoUseCase(catalog, InMemoryProgressGateway(), lock, residency)
    switch = SwitchVideoBackendUseCase(catalog, lock, residency)
    return VideoController(selected_run, catalog, switch), catalog


def test_controller_maps_shared_images_to_ltx_keyframes():
    class FakeRun(RunVideoUseCase):
        def __init__(self):
            pass

        def execute(self, job: VideoJob, backend_id: str, request_id: str) -> VideoResult:
            self.job = job
            self.backend_id = backend_id
            self.request_id = request_id
            return VideoResult(None, job.width, job.height, job.num_frames, job.frame_rate, job.seed, True)

    runner = FakeRun()
    video_controller, _ = build_video_controller(run=runner)

    response = video_controller.run(
        payload(
            backend="video-fake",
            references=[
                {
                    "name": "portrait.png",
                    "image": png_data(),
                    "frame_index": 24,
                    "strength": 0.75,
                }
            ],
        )
    )

    assert response.stub is True
    assert runner.backend_id == "video-fake"
    assert runner.request_id == "run-a"
    assert runner.job is not None
    submitted_job = runner.job
    assert submitted_job.prompt == "A kite rises above the beach"
    assert submitted_job.references[0].name == "portrait.png"
    assert (submitted_job.references[0].frame_index, submitted_job.references[0].strength) == (24, 0.75)
    assert submitted_job.references[0].png.startswith(b"\x89PNG")


def test_the_payload_says_whether_the_run_lengthens_the_prompt_again():
    """The video form's switch is the page's; the enhancer is the pipeline's. A payload that
    carries it reaches the job, and one that says nothing does not turn it on."""
    capabilities = fake_video_capabilities()

    assert video_job(payload(enhance=True), capabilities).enhance is True
    assert video_job(payload(), capabilities).enhance is False


@pytest.mark.parametrize("request_id", [None, "", 17, "x" * 129])
def test_controller_rejects_a_missing_or_invalid_request_id(request_id):
    video_controller, _ = build_video_controller(run=UnusedVideoRun())

    with pytest.raises(InvalidJob, match="request_id"):
        video_controller.run(payload(request_id=request_id))


def test_controller_normalizes_transparent_keyframes_and_assigns_a_random_seed(monkeypatch):
    monkeypatch.setattr(video_controller_module.secrets, "randbelow", lambda _limit: 42)
    submitted_job = video_job(
        payload(
            seed="",
            references=[
                {
                    "name": "transparent.png",
                    "image": transparent_png_data(),
                    "frame_index": 0,
                    "strength": 1,
                }
            ],
        ),
        fake_video_capabilities(),
    )

    with Image.open(io.BytesIO(submitted_job.references[0].png)) as image:
        assert image.mode == "RGBA" and image.size == (32, 24)
    assert submitted_job.seed == 42


@pytest.mark.parametrize(
    "values",
    [
        {"prompt": "  "},
        {"width": "960"},
        {"width": 961},
        {"height": 543},
        {"height": 1281},
        {"width": 640, "height": 640},
        {"num_frames": 8},
        {"num_frames": 145.0},
        {"num_frames": 146},
        {"num_frames": 362},
        {"frame_rate": 30},
        {"frame_rate": 24.0},
        {"seed": -1},
        {"seed": "42"},
        {"seed": 2**32},
        {"references": "not-a-list"},
        {"references": [None]},
        {"references": [{}]},
        {"references": [{"name": "frame", "image": png_data(), "frame_index": -1, "strength": 1}]},
        {"references": [{"name": "frame", "image": png_data(), "frame_index": 145, "strength": 1}]},
        {"references": [{"name": "frame", "image": png_data(), "frame_index": 0, "strength": 0}]},
        {"references": [{"name": "frame", "image": png_data(), "frame_index": 0, "strength": 1.1}]},
        {"references": [{"name": "frame", "image": png_data(), "frame_index": 0, "strength": True}]},
        {"references": [{"name": "", "image": png_data(), "frame_index": 0, "strength": 1}]},
        {
            "references": [
                {"name": str(index), "image": png_data(), "frame_index": 0, "strength": 1} for index in range(9)
            ]
        },
    ],
)
def test_controller_rejects_invalid_video_requests(values):
    video_controller, _ = build_video_controller(run=UnusedVideoRun())

    with pytest.raises(InvalidJob):
        video_controller.run(payload(**values))


def test_controller_uses_the_selected_models_frame_rate_and_reference_limit():
    capabilities = replace(fake_video_capabilities(), frame_rate=30, max_references=1)
    video_controller, _ = build_video_controller(run=UnusedVideoRun(), capabilities=capabilities)

    with pytest.raises(InvalidJob, match="frame_rate must be 30"):
        video_controller.run(payload(frame_rate=24))

    with pytest.raises(InvalidJob, match="at most 1 image references"):
        video_controller.run(payload(frame_rate=30, references=[{}, {}]))


def test_controller_uses_the_model_seed_and_reference_strength_limits():
    capabilities = replace(
        fake_video_capabilities(),
        min_seed=100,
        max_seed=200,
        min_reference_strength=0.25,
        max_reference_strength=0.75,
        reference_strength_step=0.1,
        default_reference_strength=0.5,
    )
    video_controller, _ = build_video_controller(run=UnusedVideoRun(), capabilities=capabilities)
    reference = {"name": "frame", "image": png_data(), "frame_index": 0, "strength": 0.2}
    valid_reference = {**reference, "strength": 0.5}

    with pytest.raises(InvalidJob, match="seed must be a whole number between 100 and 200"):
        video_controller.run(payload(seed=99))
    with pytest.raises(InvalidJob, match=r"strength must be between 0\.25 and 0\.75"):
        video_controller.run(payload(seed=150, references=[reference]))
    valid_job = video_job(payload(seed=150, references=[valid_reference]), capabilities)
    assert valid_job.seed == 150 and valid_job.references[0].strength == 0.5


def test_controller_rejects_a_seed_when_the_model_does_not_support_one():
    capabilities = replace(fake_video_capabilities(), min_seed=None, max_seed=None)

    with pytest.raises(InvalidJob, match="This video model does not support a seed"):
        video_job(payload(seed=42), capabilities)


def test_controller_keeps_a_blank_seed_unset_when_the_model_does_not_support_one():
    capabilities = replace(fake_video_capabilities(), min_seed=None, max_seed=None)

    submitted_job = video_job(payload(seed=""), capabilities)

    assert submitted_job.seed is None


def test_controller_rejects_unreadable_keyframe_data():
    invalid_reference = {"name": "broken", "image": "not-base64", "frame_index": 0, "strength": 1}
    video_controller, _ = build_video_controller(run=UnusedVideoRun())

    with pytest.raises(UnreadableImage):
        video_controller.run(payload(references=[invalid_reference]))


def test_controller_rejects_a_missing_keyframe_image():
    video_controller, _ = build_video_controller(run=UnusedVideoRun())

    with pytest.raises(UnreadableImage):
        video_controller.run(
            payload(
                references=[
                    {
                        "name": "missing.png",
                        "frame_index": 0,
                        "strength": 1,
                    }
                ]
            )
        )


def test_controller_switches_only_the_video_catalog():
    video_controller, catalog = build_video_controller()

    video_controller.switch({"backend": "video-other"})

    assert catalog.active_id() == "video-other"


def test_controller_rejects_a_non_text_video_backend_id():
    video_controller, _ = build_video_controller(run=UnusedVideoRun())

    with pytest.raises(InvalidJob, match="backend must be a video model id"):
        video_controller.run(payload(backend=17))
