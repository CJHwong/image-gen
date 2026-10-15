import base64
import io

import pytest
from PIL import Image

from studio.l1_entities.errors import InvalidJob, UnreadableImage
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.run_video_use_case import RunVideoUseCase
from studio.l3_interface_adapters.controllers.video_controller import VideoController


class UnusedVideoRun(RunVideoUseCase):
    def __init__(self):
        pass

    def execute(self, job: VideoJob) -> VideoResult:
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
        "references": [],
    }
    values.update(overrides)
    return values


def test_controller_maps_shared_images_to_ltx_keyframes():
    class FakeRun(RunVideoUseCase):
        def __init__(self):
            self.job: VideoJob | None = None

        def execute(self, job: VideoJob) -> VideoResult:
            self.job = job
            return VideoResult(None, job.width, job.height, job.num_frames, job.frame_rate, job.seed, True)

    runner = FakeRun()
    controller = VideoController(runner)

    response = controller.run(
        payload(
            references=[
                {
                    "name": "portrait.png",
                    "image": png_data(),
                    "frame_index": 24,
                    "strength": 0.75,
                }
            ]
        )
    )

    assert response.stub is True
    assert runner.job is not None
    submitted_job = runner.job
    assert submitted_job.prompt == "A kite rises above the beach"
    assert submitted_job.references[0].name == "portrait.png"
    assert (submitted_job.references[0].frame_index, submitted_job.references[0].strength) == (24, 0.75)
    assert submitted_job.references[0].png.startswith(b"\x89PNG")


def test_controller_normalizes_transparent_keyframes_to_png():
    from studio.l3_interface_adapters.controllers.video_controller import video_job as parse_video_job

    submitted_job = parse_video_job(
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
        )
    )

    with Image.open(io.BytesIO(submitted_job.references[0].png)) as image:
        assert image.mode == "RGBA" and image.size == (32, 24)
    assert submitted_job.seed is None


@pytest.mark.parametrize(
    "values",
    [
        {"prompt": "  "},
        {"width": "960"},
        {"width": 961},
        {"height": 543},
        {"height": 1281},
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
    request = payload(**values)

    with pytest.raises(InvalidJob):
        VideoController(UnusedVideoRun()).run(request)


def test_controller_rejects_unreadable_keyframe_data():
    invalid_reference = {"name": "broken", "image": "not-base64", "frame_index": 0, "strength": 1}

    with pytest.raises(UnreadableImage):
        VideoController(UnusedVideoRun()).run(payload(references=[invalid_reference]))


def test_controller_rejects_a_missing_keyframe_image():
    with pytest.raises(UnreadableImage):
        VideoController(UnusedVideoRun()).run(
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
