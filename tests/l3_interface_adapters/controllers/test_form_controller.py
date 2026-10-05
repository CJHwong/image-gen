"""The form the page posts, turned into use case calls.

The controller is the only place that reads a raw form value. So each test
asserts the request the use case received, not only that the method returned.
"""

import base64
import io
import json
from unittest.mock import Mock

import pytest
from PIL import Image, PngImagePlugin

from studio.l1_entities.errors import InvalidJob, UnreadableImage
from studio.l2_use_cases.describe_studio_use_case import StudioView
from studio.l2_use_cases.run_image_use_case import RunImageRequest
from studio.l3_interface_adapters.controllers.form_controller import FormController, rewrite_request, run_request
from tests.support.fakes import fake_capabilities


def encoded(fmt="PNG", size=(40, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "blue").save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode()


def reference_of(payload):
    """The one reference a form with a single base64 blob turns into."""
    return run_request({"prompt": "p", "references": json.dumps([payload])}).references[0]


@pytest.fixture
def uses():
    return {name: Mock() for name in ("describe", "run", "read_progress", "cancel", "switch", "rewrite")}


@pytest.fixture
def controller(uses):
    return FormController(**uses)


def test_the_page_is_the_view_the_use_case_returns(controller, uses):
    view = StudioView(active=fake_capabilities(), backends=(("fake", "Fake", ""), ("other", "Other", "")))
    uses["describe"].execute.return_value = view
    assert controller.page() is view


def test_a_run_is_the_form_turned_into_a_request(controller, uses):
    form = {
        "mode": "edit",
        "prompt": "make it night",
        "seed": "3",
        "steps": "8",
        "count": "2",
        "backend": "fake",
    }
    answer = Mock()
    uses["run"].execute.return_value = answer
    assert controller.run(form) is answer
    request = uses["run"].execute.call_args.args[0]
    assert isinstance(request, RunImageRequest)
    assert (request.mode, request.prompt, request.seed, request.total, request.index) == (
        "edit",
        "make it night",
        "3",
        2,
        1,
    )
    # The raw form goes through as the options, so the mode parses its own values.
    assert request.options is form and request.backend == "fake"


def test_a_rewrite_carries_the_prompt_and_the_pictures(controller, uses):
    form = {"mode": "edit", "prompt": "a cat", "references": json.dumps([encoded()])}
    answer = Mock()
    uses["rewrite"].execute.return_value = answer
    assert controller.rewrite(form) is answer
    request = uses["rewrite"].execute.call_args.args[0]
    assert (request.prompt, request.mode) == ("a cat", "edit")
    assert [(reference.width, reference.height) for reference in request.references] == [(40, 30)]


def test_the_progress_is_the_one_the_use_case_reports(controller, uses):
    state = Mock()
    uses["read_progress"].execute.return_value = state
    assert controller.progress() is state


def test_a_cancel_stops_the_run_in_flight(controller, uses):
    controller.cancel()
    assert uses["cancel"].execute.call_count == 1


@pytest.mark.parametrize("form, backend", [({"backend": "flux2"}, "flux2"), ({}, "")])
def test_a_switch_names_the_backend_from_the_form(controller, uses, form, backend):
    # A blank name reaches the use case, which refuses it as an unknown backend.
    controller.switch(form)
    assert uses["switch"].execute.call_args.args == (backend,)


def test_the_form_becomes_a_request():
    form = {
        "mode": "edit",
        "prompt": "make it night",
        "seed": "3",
        "steps": "8",
        "count": "2",
        "references": json.dumps([encoded("JPEG")]),
        "reference_token": "",
    }
    request = run_request(form)
    assert (request.mode, request.prompt, request.seed, request.total, request.index) == (
        "edit",
        "make it night",
        "3",
        2,
        1,
    )
    assert request.options["steps"] == "8"
    reference = request.references[0]
    assert (reference.width, reference.height) == (40, 30) and reference.png[:4] == b"\x89PNG"


def test_a_chain_request_carries_its_position_and_token():
    request = run_request({"prompt": "p", "total": "3", "index": "2", "reference_token": "abc", "references": "[]"})
    assert (request.mode, request.total, request.index, request.reference_token) == ("generate", 3, 2, "abc")


def test_the_form_carries_the_backend():
    assert run_request({"prompt": "p", "backend": "flux2"}).backend == "flux2"


def test_a_bad_count_is_a_form_error():
    with pytest.raises(InvalidJob, match="count must be a whole number"):
        run_request({"prompt": "p", "count": "two"})


def test_a_bad_index_is_a_form_error():
    with pytest.raises(InvalidJob, match="index must be a whole number"):
        run_request({"prompt": "p", "index": "1.5"})


def test_references_that_are_not_json_are_a_form_error():
    with pytest.raises(InvalidJob, match="references must be a JSON array"):
        run_request({"prompt": "p", "references": "not json"})


def test_a_broken_image_is_named():
    with pytest.raises(UnreadableImage, match="Could not read that reference image"):
        run_request({"prompt": "p", "references": json.dumps([base64.b64encode(b"nope").decode()])})


def test_a_rewrite_reads_the_same_pictures_a_run_would():
    # The page leaves the mask out of the form it posts here. So the rewriter sees
    # the scene, and the request holds no field for a mask at all.
    form = {"prompt": "a cat", "references": json.dumps([encoded("JPEG"), encoded("PNG")])}
    request = rewrite_request(form)
    assert (request.prompt, request.mode) == ("a cat", "generate")
    assert [(reference.width, reference.height) for reference in request.references] == [(40, 30), (40, 30)]
    assert not hasattr(request, "mask")


def test_a_rewrite_without_a_mode_is_a_generate_rewrite():
    assert rewrite_request({"prompt": "a cat"}).mode == "generate"


def test_a_rewrite_without_pictures_carries_none():
    assert rewrite_request({"prompt": "a cat", "mode": "edit"}).references == ()


def test_a_rotated_photo_is_turned_upright():
    image = Image.new("RGB", (40, 30), "blue")
    exif = image.getexif()
    exif[0x0112] = 6  # the camera was turned: show it rotated 90 degrees
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    reference = reference_of(base64.b64encode(buffer.getvalue()).decode())
    assert (reference.width, reference.height) == (30, 40)


def test_a_png_is_encoded_again_without_its_text():
    # A PNG can carry a prompt as text. Re-encoding drops it, so the engine never
    # reads a second prompt out of the picture.
    image = Image.new("RGB", (8, 8), "blue")
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", "a secret prompt")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", pnginfo=info)
    assert b"a secret prompt" not in reference_of(base64.b64encode(buffer.getvalue()).decode()).png


@pytest.mark.parametrize("mode, expected", [("CMYK", "RGB"), ("L", "RGB"), ("RGBA", "RGBA"), ("I;16", "RGB")])
def test_every_color_mode_becomes_rgb(mode, expected):
    buffer = io.BytesIO()
    Image.new(mode, (8, 8)).save(buffer, format="TIFF")
    png = reference_of(base64.b64encode(buffer.getvalue()).decode()).png
    assert Image.open(io.BytesIO(png)).mode == expected
