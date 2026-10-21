"""The JSON API: a body becomes the page's form, and the answer becomes a document."""

import base64
from typing import cast

import pytest

from studio.l1_entities.errors import InvalidJob, StudioError
from studio.l1_entities.image_job import ImageResult
from studio.l1_entities.run_progress import RunProgress
from studio.l1_entities.video_capabilities import VideoCapabilities, VideoShape
from studio.l1_entities.video_job import VideoResult
from studio.l2_use_cases.describe_studio_use_case import StudioView
from studio.l2_use_cases.rewrite_prompt_use_case import RewriteResponse
from studio.l2_use_cases.run_image_use_case import NextRun, RunImageResponse
from studio.l3_interface_adapters.api.json_api import (
    BATCH_LIMIT,
    JsonApi,
    form_value,
    image_form,
    next_form,
    reference_text,
)
from studio.l3_interface_adapters.controllers.form_controller import FormController
from studio.l3_interface_adapters.controllers.video_controller import VideoController
from studio.l3_interface_adapters.controllers.voice_controller import VoiceController
from tests.support.fakes import fake_capabilities


class FakeController(FormController):
    """The page's controller, answering with a chain of images and nothing real."""

    def __init__(self, run=None, rewrite=None, view=None, state=None):
        self.forms = []
        self._state = state
        self._runner = run
        self._rewrite = rewrite or RewriteResponse(prompt="longer words", size="1024x1024", elapsed=1.25)
        self._view = view or StudioView(active=fake_capabilities(), backends=(("fake", "Fake", ""),))
        self.cancelled = 0
        self.rewrites_cancelled = 0
        self.watches = []

    def page(self):
        return self._view

    def run(self, form):
        self.forms.append(dict(form))
        if self._runner is None:
            raise AssertionError("no run set")
        return self._runner(form)

    def run_batch(self, forms, completed, started, cancelled):
        for index, form in enumerate(forms, 1):
            started(index, len(forms))
            completed(index, self.run(form))

    def rewrite(self, form):
        self.forms.append(dict(form))
        return self._rewrite

    def progress(self):
        return self._state or RunProgress(running=True, stage="running", step=2, total=3, label="1 of 2", kind="image")

    def watch_cancel(self, identity, active, guarded_release):
        self.watches.append((identity, active, guarded_release))

    def cancel(self):
        self.cancelled += 1

    def cancel_rewrite(self):
        self.rewrites_cancelled += 1


class FakeVideo(VideoController):
    def __init__(self, error=None):
        self.payloads = []
        self.error = error

    def run(self, payload):
        self.payloads.append(payload)
        if self.error is not None:
            raise self.error
        return VideoResult(b"mp4", 8, 8, 9, 24, 7)

    def cancel(self, payload):
        self.payloads.append(payload)
        return True


def response(seed=1, next_run=None, reference=-1):
    return RunImageResponse(
        image=ImageResult(png=b"png", width=8, height=8, seed=seed, steps=3),
        mode="generate",
        prompt="a pear",
        position="1 of 1",
        elapsed=1.5,
        next_run=next_run,
        reference=reference,
    )


def batch_of(total, each_reference=False, mask=False):
    """A controller whose every answer names the next image until `total` is reached."""

    def run(form):
        index = int(form.get("index") or 1)
        if index >= total:
            return response(seed=index)
        return response(
            seed=index,
            next_run=NextRun(
                mode="generate",
                prompt="a pear",
                seed=index + 1,
                options={"size": "512x512"},
                total=total,
                index=index + 1,
                reference_token="token-" + str(index),
                backend="fake",
                each_reference=each_reference,
                mask=mask,
            ),
        )

    return FakeController(run=run)


def test_a_body_becomes_the_form_the_page_posts():
    form = image_form(
        {
            "prompt": "a pear",
            "size": "512x512",
            "seed": 7,
            "guidance": 2.5,
            "enhance": True,
            "each_reference": False,
            "nothing": None,
            "references": ["abc", {"png_base64": "data:image/png;base64,def"}],
        },
        "edit",
    )

    assert form["mode"] == "edit"
    assert form["prompt"] == "a pear"
    assert form["size"] == "512x512"
    assert form["seed"] == "7"
    assert form["guidance"] == "2.5"
    assert form["enhance"] == "1"
    assert form["each_reference"] == ""
    assert "nothing" not in form
    assert form["references"] == '["abc", "def"]'


def test_a_reference_may_come_with_the_prefix_a_browser_hands_back():
    assert reference_text("data:image/png;base64,QUJD") == "QUJD"
    assert reference_text("data:image/jpeg;base64, QUJD ") == "QUJD"
    assert reference_text({"png_base64": "QUJD"}) == "QUJD"
    assert reference_text({"data": "QUJD"}) == "QUJD"


@pytest.mark.parametrize("bad", [{}, {"png_base64": ""}, 7, None, {"data": "  "}])
def test_a_reference_that_is_not_a_string_is_refused(bad):
    with pytest.raises(InvalidJob, match="base64 string"):
        reference_text(bad)


def test_a_value_of_no_scalar_kind_is_refused():
    with pytest.raises(InvalidJob, match="must be a string"):
        form_value("prompt", {"not": "a string"})
    with pytest.raises(InvalidJob, match="array of base64 strings"):
        image_form({"references": "QUJD"}, "generate")


def test_the_batch_is_followed_to_its_end_and_answered_whole():
    controller = batch_of(3, each_reference=True, mask=True)
    answer = JsonApi(controller).image_run({"prompt": "a pear", "count": 3}, "generate")

    assert len(answer["images"]) == 3
    assert all(image["completed_at"] > 0 for image in answer["images"])
    assert [image["seed"] for image in answer["images"]] == [1, 2, 3]
    assert answer["images"][0]["png_base64"] == base64.b64encode(b"png").decode()
    # Every request after the first is the form the page's own chain would post.
    assert "index" not in controller.forms[0]
    assert [form["index"] for form in controller.forms[1:]] == ["2", "3"]
    assert controller.forms[1]["reference_token"] == "token-1"
    assert controller.forms[1]["each_reference"] == "1"
    assert controller.forms[1]["mask"] == "1"
    assert controller.forms[1]["size"] == "512x512"


def test_a_batch_that_never_ends_is_refused_at_the_limit():
    controller = batch_of(BATCH_LIMIT + 5)

    with pytest.raises(InvalidJob, match=f"at most {BATCH_LIMIT}"):
        JsonApi(controller).image_run({"prompt": "a pear"}, "generate")


def test_a_rewrite_answers_the_longer_words_and_refuses_a_stop_as_data():
    controller = FakeController()
    api = JsonApi(controller)

    assert api.image_rewrite({"prompt": "pear"}) == {"prompt": "longer words", "size": "1024x1024", "elapsed": 1.2}
    assert controller.forms[-1]["workspace"] == "image"
    assert api.video_rewrite({"prompt": "pear"}) == {"prompt": "longer words", "size": "1024x1024", "elapsed": 1.2}
    assert controller.forms[-1]["workspace"] == "video"

    controller._rewrite = RewriteResponse(prompt="pear", size=None, elapsed=0.1, cancelled=True)
    assert api.image_rewrite({"prompt": "pear"}) == {"cancelled": True}


def test_progress_is_the_page_fields_as_data():
    assert JsonApi(FakeController()).progress() == {
        "running": True,
        "stage": "running",
        "step": 2,
        "total": 3,
        "phase": 0,
        "label": "1 of 2",
        "kind": "image",
        "stopping": False,
        "request_id": None,
    }


def test_the_studio_document_names_models_and_capabilities():
    view = StudioView(
        active=fake_capabilities(),
        backends=(("fake", "Fake", ""),),
        rewrite_modes=("generate",),
        active_video=None,
    )
    document = JsonApi(FakeController(view=view)).studio()

    assert document["image"]["active"] == "fake"
    assert document["image"]["backends"] == [{"id": "fake", "name": "Fake", "description": ""}]
    assert [mode["id"] for mode in document["image"]["capabilities"]["modes"]] == ["generate", "edit"]
    assert document["video"] is None
    assert document["rewrite_modes"] == ["generate"]


def test_the_studio_document_carries_the_video_model_when_there_is_one():
    view = StudioView(
        active=fake_capabilities(),
        backends=(("fake", "Fake", ""),),
        active_video=fake_video_capabilities(),
        video_backends=(("video-fake", "Video fake", ""),),
    )
    video = JsonApi(FakeController(view=view)).studio()["video"]

    assert video["active"] == "video-fake"
    assert video["backends"] == [{"id": "video-fake", "name": "Video fake", "description": ""}]
    assert video["capabilities"]["backend_id"] == "video-fake"
    assert "capabilities" in video


def test_a_video_run_carries_the_mode_the_route_names():
    video = FakeVideo()
    api = JsonApi(FakeController(), video)

    result = api.video_run({"prompt": "a clip", "mode": "edit"}, "generate")

    assert result.mp4 == b"mp4"
    assert video.payloads[-1]["mode"] == "generate"
    assert api.cancel_video({"request_id": "r"}) is True


def test_a_studio_without_a_video_model_refuses_a_video_call():
    api = JsonApi(FakeController())

    with pytest.raises(StudioError, match="not configured"):
        api.video_run({"prompt": "a clip"}, "generate")
    with pytest.raises(StudioError, match="not configured"):
        api.cancel_video({"request_id": "r"})


def test_next_form_carries_every_field_the_page_posts():
    form = next_form(
        NextRun(
            mode="edit",
            prompt="p",
            seed=5,
            options={"size": "512x512"},
            total=2,
            index=2,
            reference_token="t",
            backend="fake",
        )
    )

    assert form == {
        "size": "512x512",
        "mode": "edit",
        "prompt": "p",
        "seed": "5",
        "total": "2",
        "index": "2",
        "reference_token": "t",
        "backend": "fake",
    }


def fake_video_capabilities() -> VideoCapabilities:
    """The video model's own record, minimal: the document is its dataclass dump."""
    return VideoCapabilities(
        backend_id="video-fake",
        name="Video fake",
        badge="24 fps",
        description="",
        shapes=(VideoShape("1:1", 384, 384),),
        default_shape_ratio="1:1",
        min_frames=9,
        max_frames=361,
        frame_step=8,
        duration_presets=(121,),
        default_frames=121,
        frame_rate=24,
        max_references=8,
        min_reference_strength=0.05,
        max_reference_strength=1.0,
        reference_strength_step=0.05,
        default_reference_strength=1.0,
        min_seed=0,
        max_seed=100,
        min_dimension=256,
        max_dimension=1280,
        dimension_step=64,
    )


def test_a_video_run_that_names_no_request_gets_one():
    """A caller that does not want to stop the render should not have to invent an id,
    but the controller needs one to tell two renders apart."""
    video = FakeVideo()

    JsonApi(FakeController(), video).video_run({"prompt": "a clip"}, "generate")
    named = video.payloads[-1]["request_id"]

    assert isinstance(named, str) and len(named) == 32
    JsonApi(FakeController(), video).video_run({"prompt": "a clip", "request_id": "mine"}, "generate")
    assert video.payloads[-1]["request_id"] == "mine"


def test_a_video_stop_without_an_id_stops_the_render_in_flight():
    """One GPU means one render, so the caller does not have to have kept its id."""
    controller = FakeController(state=RunProgress(running=True, request_id="r-1"))
    video = FakeVideo()

    assert JsonApi(controller, video).cancel_video({}) is True
    assert video.payloads[-1] == {"request_id": "r-1"}


def test_a_video_stop_with_nothing_in_flight_says_so():
    video = FakeVideo()

    with pytest.raises(InvalidJob, match="No video render"):
        JsonApi(FakeController(), video).cancel_video({})


def test_operations_record_synchronous_runs_without_reference_bytes():
    api = JsonApi(FakeController(run=lambda _: response()))
    api.image_run({"prompt": "pear", "references": [], "client_id": "tab"}, "generate")
    state = api.state()
    operation = state["operations"][0]
    assert state["active"] is None
    assert operation["status"] == "succeeded"
    assert operation["client_id"] == "tab"
    assert operation["model"] == "Fake"
    assert "references" not in operation["settings"]
    assert api.operation_result(operation["id"])["images"][0]["prompt"] == "a pear"


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"kind": "bad"}, "kind"),
        ({"kind": "image", "workspace": "bad"}, "workspace"),
        ({"kind": "video", "mode": "bad"}, "mode"),
    ],
)
def test_operations_refuse_invalid_envelopes(payload, message):
    with pytest.raises(InvalidJob, match=message):
        JsonApi(FakeController()).reserve(payload)


def test_reserved_operations_reject_other_runs_and_can_stop_before_start():
    from studio.l1_entities.errors import BackendBusy, Cancelled

    api = JsonApi(FakeController())
    operation = api.reserve({"kind": "image"})
    assert api.state()["active"]["progress"]["running"]
    with pytest.raises(BackendBusy):
        api.release_model()
    api.cancel_operation(operation["id"])
    with pytest.raises(Cancelled):
        api.execute_operation(operation, {"kind": "image"})
    assert api.operation(operation["id"])["status"] == "cancelled"


def test_async_video_and_rewrite_use_original_controller_paths(monkeypatch):
    from studio.l1_entities.rewrite_progress import RewriteProgress

    controller = FakeController()
    monkeypatch.setattr(controller, "rewrite_state", lambda: RewriteProgress(running=True, stage="writing"))
    api = JsonApi(controller, FakeVideo())
    video = api.reserve({"kind": "video"})
    api.execute_operation(video, {"kind": "video", "prompt": "clip"})
    assert api.operation_result(video["id"]).mp4 == b"mp4"
    rewrite = api.reserve({"kind": "rewrite", "workspace": "video"})
    assert api.operation(rewrite["id"])["progress"]["stage"] == "writing"
    api.cancel_operation(rewrite["id"])
    assert controller.rewrites_cancelled == 0
    api._operations.finish(rewrite["id"], {"cancelled": True})
    rewrite = api.reserve({"kind": "rewrite"})
    api.execute_operation(rewrite, {"kind": "rewrite", "prompt": "p"})
    assert api.operation_result(rewrite["id"])["prompt"] == "longer words"


def test_json_model_selection_and_release_follow_controllers(monkeypatch):
    controller = FakeController()
    video = FakeVideo()
    switched = []
    monkeypatch.setattr(controller, "switch", lambda form: switched.append(("image", form)))
    monkeypatch.setattr(controller, "release_model", lambda: switched.append("release"))
    monkeypatch.setattr(video, "switch", lambda form: switched.append(("video", form)))
    api = JsonApi(controller, video)
    with pytest.raises(InvalidJob, match="backend"):
        api.switch_backend({}, "image")
    api.switch_backend({"backend": "fake"}, "image")
    api.switch_backend({"backend": "video"}, "video")
    api.release_model()
    assert switched == [("image", {"backend": "fake"}), ("video", {"backend": "video"}), "release"]


def test_targeted_video_cancel_does_not_cancel_another_kind():
    controller = FakeController(state=RunProgress(running=True, kind="video", request_id="render"))
    video = FakeVideo()
    api = JsonApi(controller, video)
    operation = api.reserve({"kind": "video"})
    api.cancel_operation(operation["id"])
    assert video.payloads == []


def test_reserved_video_cancellation_survives_before_progress_begins():
    from studio.l1_entities.errors import Cancelled

    api = JsonApi(FakeController(state=RunProgress()), FakeVideo())
    operation = api.reserve({"kind": "video"})
    assert not api.cancellation_requested()
    api.cancel_operation(operation["id"])
    assert api.cancellation_requested()
    with pytest.raises(Cancelled):
        api.execute_operation(operation, {"kind": "video"})
    assert not api.cancellation_requested()


def test_native_batch_owns_one_operation_and_retains_each_image():
    from studio.l1_entities.errors import BackendBusy

    api = JsonApi(batch_of(2))
    first, operation = api.image_form_run({"prompt": "pear", "count": "2", "client_id": "tab"})
    assert first.next_run is not None
    assert first.next_run.options["operation_id"] == operation["id"]
    with pytest.raises(BackendBusy):
        api.image_run({"prompt": "other"}, "generate")
    form = {**next_form(first.next_run), "client_id": "tab"}
    second, same = api.image_form_run(form)
    assert second.next_run is None and same["id"] == operation["id"]
    assert api.state()["active"] is None
    assert len(api.operation_result(operation["id"])["images"]) == 2
    with pytest.raises(BackendBusy):
        api.image_form_run(form)


def test_native_batch_cancel_between_requests_keeps_partial_output():
    from studio.l1_entities.errors import BackendBusy

    api = JsonApi(batch_of(2))
    first, operation = api.image_form_run({"prompt": "pear", "count": "2", "client_id": "tab"})
    api.cancel_operation(operation["id"])
    assert first.next_run is not None
    assert api.state()["active"] is None
    assert api.operation(operation["id"])["status"] == "cancelled"
    assert len(api.operation_result(operation["id"])["images"]) == 1
    with pytest.raises(BackendBusy):
        api.image_form_run({**next_form(first.next_run), "client_id": "tab"})


def test_native_batch_refuses_invalid_index_and_records_engine_failure():
    api = JsonApi(FakeController(run=lambda _: (_ for _ in ()).throw(ValueError("failed"))))
    with pytest.raises(ValueError):
        api.image_form_run({"prompt": "pear"})
    assert api.state()["operations"][0]["status"] == "failed"
    with pytest.raises(InvalidJob, match="index"):
        api.image_form_run({"operation_id": "id", "index": "bad"})


def test_api_batch_retains_completed_images_after_a_later_failure():
    from studio.l1_entities.errors import Cancelled

    def run(form):
        if form.get("index") == "2":
            raise Cancelled("stopped")
        return response(next_run=NextRun("generate", "pear", 2, {}, 2, 2, "", "fake"))

    api = JsonApi(FakeController(run=run))
    with pytest.raises(Cancelled):
        api.image_run({"prompt": "pear", "count": 2}, "generate")
    operation = api.state()["operations"][0]
    assert operation["status"] == "cancelled" and operation["result_url"]
    assert len(api.operation_result(operation["id"])["images"]) == 1


def test_generic_image_cancel_targets_a_paused_batch():
    api = JsonApi(batch_of(2))
    _, operation = api.image_form_run({"prompt": "pear", "count": "2"})
    api.cancel_image()
    assert api.state()["active"] is None
    assert api.operation(operation["id"])["status"] == "cancelled"


def test_generic_rewrite_cancel_targets_its_operation():
    api = JsonApi(FakeController())
    operation = api.reserve({"kind": "rewrite"})
    api.cancel_rewrite()
    assert api.cancellation_requested()
    assert isinstance(api._controller, FakeController)
    assert api._controller.rewrites_cancelled == 0
    api._operations.fail(operation["id"], ValueError("done"))


def test_structured_image_looks_and_templates_use_the_requested_capabilities(monkeypatch):
    from dataclasses import replace

    from studio.l1_entities.capabilities import LookRow, Template

    controller = batch_of(1)
    original = controller.page().active
    mode = replace(
        original.mode("generate"),
        looks=(LookRow("Light", (("Soft", "Soft window light."),)),),
        templates=(Template("Portrait", "", "A portrait of [subject]."),),
    )
    capabilities = replace(original, modes=(mode,))
    requested = []
    switched = []
    monkeypatch.setattr(controller, "switch", switched.append)
    controller.capabilities = lambda backend: requested.append(backend) or capabilities
    api = JsonApi(controller)
    api.image_run(
        {
            "backend": "chosen",
            "template": "Portrait",
            "template_values": {"subject": "a woman"},
            "looks": {"Light": "Soft"},
        },
        "generate",
    )
    assert requested == ["chosen"]
    assert switched == [{"backend": "chosen"}]
    assert controller.forms[0]["prompt"] == "A portrait of a woman. Soft window light."
    assert "looks" not in controller.forms[0]
    payload = {"kind": "image", "items": [{"template": "Portrait", "template_values": {"subject": "a child"}}]}
    operation = api.reserve(payload)
    manifest = api.execute_operation(operation, payload)
    assert manifest["items"][0]["prompt"] == "A portrait of a child."
    assert manifest["items"][0]["settings"]["template"] == "Portrait"


def test_per_reference_prompts_follow_the_whole_batch():
    from dataclasses import replace

    controller = batch_of(3)
    original = controller.page().active
    capabilities = replace(original, modes=(replace(original.mode("generate"), each_reference=True),))
    controller.capabilities = lambda backend: capabilities
    JsonApi(controller).image_run(
        {
            "prompt": "Change the wall",
            "references": ["a", "b"],
            "each_reference": True,
            "per_reference_prompts": ["blue", "green"],
            "count": 3,
        },
        "generate",
    )
    assert [form["prompt"] for form in controller.forms] == [
        "Change the wall. blue",
        "Change the wall. green",
        "Change the wall. blue",
    ]


def test_video_prompt_aids_follow_its_mode_and_templates(monkeypatch):
    from dataclasses import replace

    from studio.l1_entities.capabilities import LookRow, Template
    from studio.l1_entities.video_capabilities import VideoMode

    capabilities = replace(
        fake_video_capabilities(),
        modes=(
            VideoMode("generate", "Generate", looks=(LookRow("Camera", (("Fixed", "Fixed camera."),)),)),
            VideoMode("edit", "Edit"),
        ),
        templates=(Template("Scene", "", "A [subject] rests on a table."),),
    )
    video = FakeVideo()
    monkeypatch.setattr(video, "capabilities", lambda backend: capabilities)
    api = JsonApi(FakeController(), video)
    api.video_run(
        {"template": "Scene", "template_values": {"subject": "teapot"}, "looks": {"Camera": "Fixed"}}, "generate"
    )
    assert video.payloads[-1]["prompt"] == "A teapot rests on a table. Fixed camera."
    with pytest.raises(InvalidJob, match="Choose a template"):
        api.video_run({"template": "Scene"}, "edit")

    def run_batch(payloads, completed, started, cancelled):
        for index, payload in enumerate(payloads, 1):
            started(index, len(payloads))
            completed(index, video.run(payload))

    monkeypatch.setattr(video, "run_batch", run_batch)
    payload = {
        "kind": "video",
        "items": [
            {"template": "Scene", "template_values": {"subject": "cup"}, "looks": {"Camera": "Fixed"}},
            {"prompt": "A river.", "looks": {"Camera": "Fixed"}},
        ],
    }
    operation = api.reserve(payload)
    manifest = api.execute_operation(operation, payload)
    assert [item["prompt"] for item in video.payloads[-2:]] == [
        "A cup rests on a table. Fixed camera.",
        "A river. Fixed camera.",
    ]
    assert manifest["items"][0]["prompt"] == "A cup rests on a table. Fixed camera."
    assert manifest["items"][0]["settings"]["template"] == "Scene"
    assert manifest["items"][0]["settings"]["looks"] == {"Camera": "Fixed"}


def test_image_operation_cancel_preserves_guarded_escalation():
    from studio.l1_entities.errors import BackendBusy

    controller = FakeController()
    api = JsonApi(controller)
    operation = api.reserve({"kind": "image"})
    api.cancel_operation(operation["id"])
    identity, active, guard = controller.watches[0]
    assert identity == operation["id"] and active()

    def release():
        api._operations.finish(operation["id"], {"images": []})
        with pytest.raises(BackendBusy):
            api.reserve({"kind": "video"})
        with pytest.raises(BackendBusy):
            api.release_model()

    guard(release)
    newer = api.reserve({"kind": "video"})
    assert not active()
    guard(lambda: pytest.fail("A cancel released B"))
    assert api.state()["active"]["id"] == newer["id"]


def test_model_switch_and_release_cannot_race_an_operation_reservation(monkeypatch):
    from studio.l1_entities.errors import BackendBusy

    controller = FakeController()
    api = JsonApi(controller)
    calls = []

    def control(*arguments):
        calls.append(arguments)
        with pytest.raises(BackendBusy):
            api.reserve({"kind": "image"})

    monkeypatch.setattr(controller, "switch", control)
    monkeypatch.setattr(controller, "release_model", control)
    api.switch_backend({"backend": "fake"}, "image")
    api.release_model()
    assert calls == [({"backend": "fake"},), ()]
    assert api.reserve({"kind": "image"})["status"] == "running"


class FakeVoice(VoiceController):
    def __init__(self):
        from studio.l3_interface_adapters.gateways.auk_voice.capabilities import auk_capabilities

        self._catalog = None
        self._switch = None
        self._capabilities = auk_capabilities("flash")
        self.payloads = []

    def capabilities(self):
        return {"backend_id": "auk", "name": "AuK Flash"}

    def run(self, payload):
        from studio.l1_entities.voice_job import SpeechResult

        self.payloads.append(payload)
        return SpeechResult(b"wav", 1.2, 24000, 7, 4)

    def run_batch(self, payloads, completed, started, cancelled):
        for index, payload in enumerate(payloads, 1):
            started(index, len(payloads))
            completed(index, self.run(payload))


def test_voice_operation_discovery_and_retained_audio():
    voice = FakeVoice()
    api = JsonApi(FakeController(), voice=voice)
    assert api.studio()["voice"]["active"] == "auk"
    assert api.voice_capabilities()["name"] == "AuK Flash"
    operation = api.reserve({"kind": "voice", "text": "Hello", "voice": "warm"})
    assert operation["workspace"] == "voice" and operation["mode"] == "design"
    assert operation["prompt"] == "Hello"
    result = api.execute_operation(operation, {"text": "Hello", "voice": "warm"})
    assert api.operation_result(operation["id"]) == result
    assert api.operation(operation["id"])["seconds"] == 1.2
    assert "reference" not in operation["settings"]


def test_voice_is_optional():
    api = JsonApi(FakeController())
    with pytest.raises(StudioError, match="Voice generation"):
        api.voice_capabilities()


@pytest.mark.parametrize("kind", ["image", "video", "voice"])
def test_explicit_batches_keep_each_result(kind):
    from types import SimpleNamespace

    from studio.l1_entities.voice_job import SpeechResult

    result = VideoResult(b"mp4", 8, 8, 9, 24, 7) if kind == "video" else SpeechResult(b"wav", 1, 24000, 7, 4)

    def run_batch(payloads, completed, started, cancelled):
        for index, _payload in enumerate(payloads, 1):
            started(index, len(payloads))
            completed(index, result)

    controller = batch_of(1)
    api = JsonApi(controller, cast(VideoController, SimpleNamespace(run_batch=run_batch)), FakeVoice())
    payload = {"kind": kind, "items": [{"prompt": "one", "text": "one"}, {"prompt": "two", "text": "two"}]}
    operation = api.reserve(payload)
    assert operation["batch_total"] == 2
    assert "batch_index" not in operation
    manifest = api.execute_operation(operation, payload)
    assert manifest["batch_total"] == 2 and manifest["completed"] == 2
    assert [item["index"] for item in manifest["items"]] == [1, 2]
    assert api.item_result(operation["id"], 1)
    assert api.operation(operation["id"])["batch_index"] == 2
    with pytest.raises(LookupError):
        api.item_result(operation["id"], 3)
    if kind == "video":
        assert manifest["items"][0]["width"] == 8
        assert manifest["items"][0]["height"] == 8
        assert manifest["items"][0]["num_frames"] == 9
        assert manifest["items"][0]["frame_rate"] == 24
        assert manifest["items"][0]["seed"] == 7
    if kind == "voice":
        assert manifest["items"][0]["seconds"] == 1.2


def test_batch_keeps_earlier_items_when_a_later_image_fails():
    calls = []

    def run(form):
        calls.append(form)
        if len(calls) == 2:
            raise InvalidJob("the second item failed")
        return response()

    api = JsonApi(FakeController(run=run))
    payload = {"kind": "image", "items": [{"prompt": "one"}, {"prompt": "two"}]}
    operation = api.reserve(payload)
    with pytest.raises(InvalidJob, match="second item"):
        api.execute_operation(operation, payload)
    assert api.operation(operation["id"])["status"] == "failed"
    assert api.operation_result(operation["id"])["completed"] == 1
    assert api.item_result(operation["id"], 1)["images"]


def test_readonly_backend_capabilities_do_not_switch_models(monkeypatch):
    from types import SimpleNamespace

    from studio.l1_entities.errors import UnknownBackend

    controller = FakeController()
    monkeypatch.setattr(controller, "capabilities", lambda backend_id: fake_capabilities())
    api = JsonApi(
        controller, cast(VideoController, SimpleNamespace(capabilities=lambda backend_id: fake_video_capabilities()))
    )
    assert api.backend_capabilities("image", "fake")["backend_id"] == "fake"
    assert api.backend_capabilities("video", "video-fake")

    def missing(backend_id):
        raise UnknownBackend("not found")

    monkeypatch.setattr(controller, "capabilities", missing)
    with pytest.raises(LookupError):
        api.backend_capabilities("image", "missing")


def test_operation_workspace_must_match_its_media_kind():
    api = JsonApi(FakeController())
    with pytest.raises(InvalidJob, match="workspace must match"):
        api.reserve({"kind": "voice", "workspace": "video"})


def test_batch_progress_accounts_for_completed_items():
    api = JsonApi(FakeController())
    operation = api.reserve({"kind": "image"})
    api._operations.batch_started(operation["id"], 2, 4)
    progress = api.operation(operation["id"])["progress"]
    assert progress["step"] == 5 and progress["total"] == 12
    api._operations.batch_completed(operation["id"], {"images": []}, {"index": 1})
    api._operations.finish(operation["id"], {"items": []})
    progress = api.operation(operation["id"])["progress"]
    assert progress["step"] == 1 and progress["total"] == 4


def test_voice_batch_progress_never_repeats_a_finished_take_on_the_next_index(monkeypatch):
    import threading
    from unittest.mock import Mock

    from studio.l1_entities.voice_job import SpeechResult
    from studio.l2_use_cases.run_voice_use_case import RunVoiceUseCase
    from studio.l3_interface_adapters.gateways.auk_voice.capabilities import auk_capabilities
    from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway

    progress = InMemoryProgressGateway()
    backend = Mock()
    use_case = RunVoiceUseCase(backend, progress, threading.Lock(), Mock())
    controller = FakeController()
    monkeypatch.setattr(controller, "progress", progress.snapshot)
    api = JsonApi(controller, voice=VoiceController(use_case, auk_capabilities("flash")))
    payload = {"kind": "voice", "voice": "A clear calm narrator.", "items": [{"text": "One."}, {"text": "Two."}]}
    operation = api.reserve(payload)
    fractions = []

    def sample():
        state = api.operation(operation["id"])["progress"]
        fractions.append(state["step"] / state["total"])

    original_started = api._operations.batch_started

    def started(operation_id, index, total):
        original_started(operation_id, index, total)
        sample()

    def generate(job, on_step, should_stop):
        total = 8 if job.mode == "design" else 4
        for step in range(total + 1):
            on_step(step, total)
            sample()
        return SpeechResult(b"wav", 1, 16000, job.seed, total)

    monkeypatch.setattr(api._operations, "batch_started", started)
    backend.run.side_effect = generate
    api.execute_operation(operation, payload)
    sample()
    assert fractions == sorted(fractions)
    assert fractions[0] == 0 and fractions[-1] == 1


def test_explicit_backend_must_be_text():
    api = JsonApi(FakeController())
    with pytest.raises(InvalidJob, match="backend must be a model id"):
        api.image_run({"backend": 5, "prompt": "pear"}, "generate")


def test_optional_video_catalog_does_not_force_an_unavailable_switch():
    api = JsonApi(FakeController(), FakeVideo())
    api._select_requested_backend("video", {"backend": "video-fake"})


@pytest.mark.parametrize("each_reference", [False, True])
def test_native_image_batch_shared_progress_keeps_completed_fraction(each_reference):
    from dataclasses import replace

    controller = batch_of(4, each_reference=each_reference)
    api = JsonApi(controller)
    snapshots = []
    original_run = controller._runner

    def run(form):
        index = int(form.get("index") or 1)
        for step, total in ((0, 0), (0, 8), (1, 8), (8, 8)):
            controller._state = RunProgress(
                running=True,
                stage="running" if total else "preparing",
                step=step,
                total=total,
                label=f"{index} of 4",
                kind="image",
            )
            active = api.state()["active"]
            assert active is not None and "batch_total" not in active
            shared = active["progress"]
            snapshots.append(shared["step"] / shared["total"])
            assert api.progress()["step"] == step and api.progress()["total"] == total
        assert original_run is not None
        return original_run(form)

    controller._runner = run
    first, operation = api.image_form_run(
        {"prompt": "pear", "count": "4", "each_reference": "on" if each_reference else ""}
    )
    current = first
    while current.next_run is not None:
        current, _ = api.image_form_run(next_form(current.next_run))
    assert snapshots == sorted(snapshots)
    assert snapshots[3:7] == [0.25, 0.25, 0.25, 0.28125]
    assert len(api.operation_result(operation["id"])["images"]) == 4
    controller._state = replace(controller._state, label="4 of 4")
    assert api.operation(operation["id"])["progress"]["stage"] == "succeeded"


@pytest.mark.parametrize("label", ["", "1 image", "1 of 1", "0 of 4", "5 of 4", "2 of 0", "two of 4", "2 of 4 extra"])
def test_native_image_progress_ignores_non_batch_labels(label):
    controller = FakeController(state=RunProgress(running=True, step=2, total=8, label=label))
    api = JsonApi(controller)
    operation = api.reserve({"kind": "image"}, source="ui")
    assert api.operation(operation["id"])["progress"] == api.progress()


def test_stopping_native_image_batch_keeps_completed_fraction():
    controller = FakeController(state=RunProgress(running=True, step=0, total=0, label="2 of 4", stopping=True))
    api = JsonApi(controller)
    operation = api.reserve({"kind": "image"}, source="ui")
    api.cancel_operation(operation["id"])
    shared = api.operation(operation["id"])
    assert shared["status"] == "stopping"
    assert shared["progress"]["step"] / shared["progress"]["total"] == 0.25
    assert shared["progress"]["stopping"] is True


@pytest.mark.parametrize("kind,source", [("image", "api"), ("video", "ui"), ("rewrite", "ui")])
def test_native_image_progress_label_does_not_change_other_operations(kind, source, monkeypatch):
    controller = FakeController(state=RunProgress(running=True, step=2, total=8, label="2 of 4"))
    api = JsonApi(controller)
    operation = api.reserve({"kind": kind}, source=source)
    monkeypatch.setattr(api, "rewrite_state", lambda: {"stage": "writing"})
    expected = api.rewrite_state() if kind == "rewrite" else api.progress()
    assert api.operation(operation["id"])["progress"] == expected


def test_omitted_voice_mode_uses_the_active_backend_default():
    from unittest.mock import Mock

    from studio.l3_interface_adapters.gateways.drama_voice.capabilities import drama_capabilities

    voice = VoiceController(Mock(), drama_capabilities())
    api = JsonApi(FakeController(), voice=voice)
    operation = api.reserve({"kind": "voice", "text": "Hello"})
    assert operation["mode"] == "generate" and operation["backend"] == "drama3"
