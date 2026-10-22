import base64
import io
import threading
from dataclasses import replace

import pytest
from PIL import Image

from studio.l1_entities.errors import InvalidJob, UnreadableImage, UnsupportedMode
from studio.l1_entities.video_capabilities import VideoAdapter, VideoMode, VideoShape
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


def test_video_batch_validates_every_item_before_any_engine_call():
    controller, _ = build_video_controller(run=UnusedVideoRun())
    with pytest.raises(InvalidJob, match="prompt"):
        controller.run_batch(
            [payload(), payload(prompt="")], lambda index, result: None, lambda index, total: None, lambda: False
        )


def test_video_batch_rejects_different_backends():
    controller, _ = build_video_controller(run=UnusedVideoRun())
    with pytest.raises(InvalidJob, match="same backend"):
        controller.run_batch(
            [payload(backend="video-fake"), payload(backend="video-other")],
            lambda index, result: None,
            lambda index, total: None,
            lambda: False,
        )


def test_video_batch_returns_each_result_with_one_request_identity():
    controller, _ = build_video_controller()
    completed = []
    started = []
    results = controller.run_batch(
        [payload(), payload(prompt="The dog runs", seed=7)],
        lambda index, result: completed.append((index, result.seed)),
        lambda index, total: started.append((index, total)),
        lambda: False,
    )
    assert [result.seed for result in results] == [42, 7]
    assert completed == [(1, 42), (2, 7)]
    assert started == [(1, 2), (2, 2)]


def test_video_batch_rejects_an_empty_list():
    controller, _ = build_video_controller()
    with pytest.raises(InvalidJob, match="empty"):
        controller.run_batch([], lambda index, result: None, lambda index, total: None, lambda: False)


def test_video_batch_rejects_a_backend_that_is_not_a_string():
    controller, _ = build_video_controller()
    with pytest.raises(InvalidJob, match="backend"):
        controller.run_batch([payload(backend=5)], lambda index, result: None, lambda index, total: None, lambda: False)


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


@pytest.mark.parametrize("settings", [{}, {"enhance": False}, {"enhance": True}])
def test_generation_always_enables_the_pipeline_enhancer(settings):
    assert video_job(payload(**settings), fake_video_capabilities()).enhance is True


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


def editing_capabilities(adapter=None, **overrides):
    """The fake model with a mode switch and one adapter, which is what an edit needs."""
    declared = adapter or VideoAdapter(
        id="relight",
        label="Relight",
        hint="Change the light of a clip",
        mode="edit",
        file="relight.safetensors",
        prompt="A night version of the same place.",
        strength=1.0,
        stage_2_conditioning=True,
    )
    return replace(
        fake_video_capabilities(),
        modes=(
            VideoMode("generate", "Generate", accepts_audio=True),
            VideoMode("edit", "Edit", needs_clip=True),
        ),
        adapters=(declared,),
        **overrides,
    )


def clip_payload(**overrides):
    values = {"name": "input.mp4", "data": base64.b64encode(b"clip bytes").decode("ascii")}
    values.update(overrides)
    return values


def audio_payload(**overrides):
    values = {"name": "theme.wav", "data": base64.b64encode(b"RIFF\x24\x00\x00\x00WAVEfmt ").decode("ascii")}
    values.update(overrides)
    return values


def test_a_generate_job_carries_the_track_and_the_name_it_came_in_with():
    """The bytes travel as they arrived: the runner hands them to the engine's own
    environment, which decodes the container and writes the stereo PCM the model takes."""
    job = video_job(payload(audio=audio_payload()), editing_capabilities())

    assert job.audio is not None
    assert job.audio.name == "theme.wav"
    assert job.audio.data.startswith(b"RIFF")


@pytest.mark.parametrize(
    "data",
    [
        b"RIFF\x24\x00\x00\x00WAVEfmt ",
        b"fLaC\x00\x00\x00\x22",
        b"OggS\x00\x02",
        b"FORM\x00\x00\x00\x00AIFF",
        b"FORM\x00\x00\x00\x00AIFC",
        b"\x00\x00\x00\x20ftypM4A ",
        b"ID3\x04\x00\x00",
        b"\xff\xfb\x90\x00",
    ],
)
def test_every_audio_container_the_decoder_reads_is_accepted(data):
    job = video_job(
        payload(audio={"name": "track", "data": base64.b64encode(data).decode("ascii")}),
        editing_capabilities(),
    )

    assert job.audio is not None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"audio": {"name": "theme.wav", "data": ""}}, "Could not read that audio"),
        ({"audio": {"name": "theme.wav", "data": "not base64!"}}, "Could not read that audio"),
        ({"audio": {"data": base64.b64encode(b"RIFF\x00\x00\x00\x00WAVE").decode("ascii")}}, "needs a name"),
        ({"audio": "theme.wav"}, "audio must be an object"),
        (
            {"audio": {"name": "notes.txt", "data": base64.b64encode(b"hello, not audio").decode("ascii")}},
            "not audio this model reads",
        ),
    ],
)
def test_a_track_the_form_could_not_have_sent_is_refused(overrides, message):
    with pytest.raises(InvalidJob, match=message):
        video_job(payload(**overrides), editing_capabilities())


def test_a_track_past_the_model_s_limit_is_refused_before_the_run():
    capabilities = replace(editing_capabilities(), max_audio_megabytes=0.000001)

    with pytest.raises(InvalidJob, match="larger than"):
        video_job(payload(audio=audio_payload()), capabilities)


def test_an_edit_refuses_a_track_because_the_clip_is_its_whole_input():
    with pytest.raises(InvalidJob, match="Audio is a Generate input"):
        video_job(
            payload(mode="edit", adapter="relight", clip=clip_payload(), audio=audio_payload()),
            editing_capabilities(),
        )


def test_an_edit_job_carries_the_clip_and_the_adapter_it_was_measured_with():
    """The controller resolves the adapter's own facts and hands them to the job, so the
    runner builds a command from the job alone: the file's name, the strength, and the flag
    that keeps stage 2 conditioned, which is what stopped a stall turning into a car."""
    capabilities = editing_capabilities()

    job = video_job(
        payload(mode="edit", adapter="relight", adapter_strength=0.8, clip=clip_payload()),
        capabilities,
    )

    assert job.edit is not None
    assert job.edit.adapter == "relight"
    assert job.edit.strength == 0.8
    assert job.edit.lora_file == "relight.safetensors"
    assert job.edit.clip == b"clip bytes"
    assert job.edit.clip_name == "input.mp4"
    assert job.edit.stage_2_conditioning is True


def test_a_doubling_edit_may_ask_for_twice_a_declared_shape():
    """The upscaler's card wants a reference at half the target's linear resolution, so the
    one adapter that declares it may ask for a shape the ladder does not hold: twice one
    that it does. A shape that is not twice a declared rung is still refused."""
    capabilities = editing_capabilities(
        VideoAdapter(
            id="upscale",
            label="Upscale",
            hint="Twice the size",
            mode="edit",
            file="upscale.safetensors",
            prompt="The same shot.",
            doubles_output=True,
        ),
        shapes=(VideoShape("1:1", 512, 512),),
    )

    job = video_job(
        payload(mode="edit", adapter="upscale", clip=clip_payload(), width=1024, height=1024),
        capabilities,
    )

    assert (job.width, job.height) == (1024, 1024)
    with pytest.raises(InvalidJob, match="supported video shape"):
        video_job(
            payload(mode="edit", adapter="upscale", clip=clip_payload(), width=896, height=896),
            capabilities,
        )


def test_an_edit_that_does_not_double_refuses_the_doubled_shape():
    capabilities = editing_capabilities(shapes=(VideoShape("1:1", 512, 512),))

    with pytest.raises(InvalidJob, match="supported video shape"):
        video_job(
            payload(mode="edit", adapter="relight", clip=clip_payload(), width=1024, height=1024),
            capabilities,
        )


def test_an_edit_strength_left_blank_takes_the_adapter_itself():
    capabilities = editing_capabilities()

    job = video_job(payload(mode="edit", adapter="relight", clip=clip_payload()), capabilities)

    assert job.edit is not None
    assert job.edit.strength == 1.0


def test_a_run_that_names_no_mode_draws_a_clip():
    """A page from before the mode switch sends no mode, and gets the run it always got."""
    job = video_job(payload(), editing_capabilities())

    assert job.edit is None
    assert video_job(payload(mode=""), editing_capabilities()).edit is None
    assert video_job(payload(mode="generate"), editing_capabilities()).edit is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"adapter": "relight"}, "needs a clip"),
        ({"clip": clip_payload(), "adapter": "other"}, "adapter must be one of relight"),
        ({"clip": clip_payload()}, "adapter must be one of relight"),
        ({"clip": clip_payload(), "adapter": "relight", "adapter_strength": 9.0}, "adapter_strength"),
        ({"clip": clip_payload(), "adapter": "relight", "adapter_strength": True}, "adapter_strength"),
        ({"clip": clip_payload(), "adapter": "relight", "adapter_strength": "strong"}, "adapter_strength"),
        ({"clip": {"data": "AAAA"}, "adapter": "relight"}, "needs a name"),
        ({"clip": {"name": "in.mp4", "data": ""}, "adapter": "relight"}, "Could not read that clip"),
        ({"clip": {"name": "in.mp4", "data": "not base64!"}, "adapter": "relight"}, "Could not read that clip"),
        ({"clip": "a-path.mp4", "adapter": "relight"}, "needs a clip"),
    ],
)
def test_an_edit_that_the_form_could_not_have_made_is_refused(overrides, message):
    with pytest.raises(InvalidJob, match=message):
        video_job(payload(mode="edit", **overrides), editing_capabilities())


def test_a_clip_past_the_model_s_limit_is_refused_before_the_run():
    capabilities = editing_capabilities(max_clip_megabytes=0.000001)

    with pytest.raises(InvalidJob, match="larger than"):
        video_job(payload(mode="edit", adapter="relight", clip=clip_payload()), capabilities)


def test_an_edit_mode_with_no_adapter_declared_is_refused():
    capabilities = replace(editing_capabilities(), adapters=())

    with pytest.raises(InvalidJob, match="no edit adapter"):
        video_job(payload(mode="edit", adapter="relight", clip=clip_payload()), capabilities)


def test_a_mode_the_model_does_not_have_is_refused():
    with pytest.raises(UnsupportedMode, match="no restore mode"):
        video_job(payload(mode="restore"), editing_capabilities())


def test_a_mode_that_is_not_a_string_is_refused():
    with pytest.raises(InvalidJob, match="mode must be a string"):
        video_job(payload(mode=17), editing_capabilities())


def test_an_effect_runs_at_the_geometry_its_card_trained_at():
    """960 x 544 does not sit on the 64 pixel grid, so the adapter's own pair decides the
    size instead of the ladder, and the card's frame count is the only one accepted."""
    adapter = VideoAdapter(
        id="relight",
        label="Relight",
        hint="Change the light of a clip",
        mode="edit",
        file="relight.safetensors",
        prompt="A night version of the same place.",
        width=960,
        height=544,
        num_frames=97,
    )
    capabilities = editing_capabilities(adapter)

    job = video_job(
        payload(mode="edit", adapter="relight", clip=clip_payload(), width=544, height=960, num_frames=97),
        capabilities,
    )
    assert (job.width, job.height, job.num_frames) == (544, 960, 97)

    with pytest.raises(InvalidJob, match="960 by 544"):
        video_job(
            payload(mode="edit", adapter="relight", clip=clip_payload(), width=384, height=384, num_frames=97),
            capabilities,
        )
    with pytest.raises(InvalidJob, match="97 frames"):
        video_job(
            payload(mode="edit", adapter="relight", clip=clip_payload(), width=960, height=544, num_frames=121),
            capabilities,
        )


def test_controller_reads_capabilities_without_switching():
    selected, catalog = build_video_controller()
    assert selected.capabilities().backend_id == catalog.active_id()
    assert selected.capabilities(catalog.active_id()) == catalog.get(catalog.active_id()).capabilities()


@pytest.mark.parametrize("value", [True, False])
def test_fast_mode_is_validated_and_carried_by_the_video_job(value):
    from dataclasses import replace

    capabilities = replace(fake_video_capabilities(), fast_mode=True)
    assert video_job(payload(fast_mode=value), capabilities).fast_mode is value


@pytest.mark.parametrize("value", [None, "true", 0, 1, [], {}])
def test_fast_mode_rejects_non_boolean_values(value):
    with pytest.raises(InvalidJob, match="boolean"):
        video_job(payload(fast_mode=value), fake_video_capabilities())


def test_fast_mode_rejects_an_unsupported_model_and_defaults_to_off():
    assert video_job(payload(), fake_video_capabilities()).fast_mode is False
    with pytest.raises(InvalidJob, match="does not support Fast mode"):
        video_job(payload(fast_mode=True), fake_video_capabilities())


def test_video_batch_rejects_mixed_fast_mode_before_running():
    from dataclasses import replace

    controller, _ = build_video_controller(
        run=UnusedVideoRun(), capabilities=replace(fake_video_capabilities(), fast_mode=True)
    )
    with pytest.raises(InvalidJob, match="same fast_mode"):
        controller.run_batch(
            [payload(fast_mode=True), payload(fast_mode=False)],
            lambda *_: None,
            lambda *_: None,
            lambda: False,
        )
