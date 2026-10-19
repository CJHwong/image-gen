"""The JSON API: a body becomes the page's form, and the answer becomes a document."""

import base64

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
from tests.support.fakes import fake_capabilities


class FakeController(FormController):
    """The page's controller, answering with a chain of images and nothing real."""

    def __init__(self, run=None, rewrite=None, view=None):
        self.forms = []
        self._runner = run
        self._rewrite = rewrite or RewriteResponse(prompt="longer words", size="1024x1024", elapsed=1.25)
        self._view = view or StudioView(active=fake_capabilities(), backends=(("fake", "Fake", ""),))
        self.cancelled = 0
        self.rewrites_cancelled = 0

    def page(self):
        return self._view

    def run(self, form):
        self.forms.append(dict(form))
        if self._runner is None:
            raise AssertionError("no run set")
        return self._runner(form)

    def rewrite(self, form):
        self.forms.append(dict(form))
        return self._rewrite

    def progress(self):
        return RunProgress(running=True, stage="running", step=2, total=3, label="1 of 2", kind="image")

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
