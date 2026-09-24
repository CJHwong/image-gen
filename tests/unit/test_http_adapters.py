import base64
import html
import io
import json
import re

import pytest
from PIL import Image, PngImagePlugin

from studio.l1_entities.errors import (
    BackendBusy,
    Cancelled,
    InvalidJob,
    MissingPrompt,
    ReferenceExpired,
    UnreadableImage,
)
from studio.l1_entities.image_job import ImageResult
from studio.l1_entities.run_progress import RunProgress
from studio.l2_use_cases.describe_studio_use_case import StudioView
from studio.l2_use_cases.run_image_use_case import NextRun, RunImageResponse
from studio.l3_interface_adapters.controllers.form_controller import run_request
from studio.l3_interface_adapters.presenters.html_presenter import HtmlPresenter
from tests.unit.fakes import fake_capabilities


def encoded(fmt="PNG", size=(40, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "blue").save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode()


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


def test_a_broken_image_is_named():
    with pytest.raises(UnreadableImage, match="Could not read that reference image"):
        run_request({"prompt": "p", "references": json.dumps([base64.b64encode(b"nope").decode()])})


def test_a_bad_count_is_a_form_error():
    with pytest.raises(InvalidJob, match="count must be a whole number"):
        run_request({"prompt": "p", "count": "two"})


PAGE = "<title>__NAME__</title><input value=__BACKEND__><b>__BADGE__</b><script>const STUDIO = __STUDIO__;</script>"


def presenter():
    return HtmlPresenter(PAGE)


def test_the_page_carries_the_capabilities():
    caps = fake_capabilities(name="Fake </script> engine")
    body = presenter().page(StudioView(active=caps, backends=(("fake", "Fake"),)))
    assert "<title>Fake &lt;/script&gt; engine</title>" in body and "<b>bf16</b>" in body
    assert "<input value=fake>" in body  # the form names the backend it was built for
    data = re.search(r"const STUDIO = (.*);</script>", body)
    assert data
    studio = json.loads(data.group(1))
    assert studio["backend"]["max_batch"] == 4 and studio["backends"] == [["fake", "Fake"]]
    edit = studio["modes"][1]
    assert edit["id"] == "edit" and edit["min_references"] == 1 and edit["params"][0]["id"] == "steps"
    assert "</script>" not in body.split("const STUDIO = ")[1].split(";</script>")[0]


def response(next_run=None):
    image = ImageResult(png=b"\x89PNGdata", width=640, height=480, seed=9, steps=8)
    return RunImageResponse(
        image=image, mode="generate", prompt='a "red" apple', position="1 of 2", elapsed=12.4, next_run=next_run
    )


def test_an_image_becomes_an_item():
    body = presenter().run(response())
    assert 'data-seed="9"' in body and 'data-width="640"' in body and 'data-elapsed="12"' in body
    assert 'data-prompt="a &quot;red&quot; apple"' in body and 'data-position="1 of 2"' in body
    assert base64.b64encode(b"\x89PNGdata").decode() in body and "chain" not in body


def test_a_batch_adds_the_next_request():
    nxt = NextRun(
        mode="generate",
        prompt="p",
        seed=10,
        options={"steps": "8"},
        total=2,
        index=2,
        reference_token="tok",
        backend="fake",
    )
    body = presenter().run(response(nxt))
    chain = re.search(r"hx-vals='([^']*)'", body)
    assert chain
    values = json.loads(html.unescape(chain.group(1)))
    assert values == {
        "steps": "8",
        "mode": "generate",
        "prompt": "p",
        "seed": "10",
        "total": "2",
        "index": "2",
        "reference_token": "tok",
        "backend": "fake",
    }
    assert 'data-progress="2 of 2"' in body


@pytest.mark.parametrize(
    "error, text",
    [
        (InvalidJob("steps must be at least 1"), '<div class="err">Bad form value: steps must be at least 1</div>'),
        (MissingPrompt("A prompt is required."), '<div class="err">A prompt is required.</div>'),
        (
            ReferenceExpired("The reference image expired. Pick it again."),
            '<div class="err">The reference image expired. Pick it again.</div>',
        ),
        (BackendBusy("Wait"), '<div class="err">Wait</div>'),
        (Cancelled("stopped at step 3"), '<div class="hint">Cancelled (stopped at step 3).</div>'),
        (RuntimeError("out of <memory>"), '<div class="err">RuntimeError: out of &lt;memory&gt;</div>'),
    ],
)
def test_failures_become_one_line(error, text):
    assert presenter().failure(error) == text


def test_progress_carries_numbers_and_the_next_poll():
    body = presenter().progress(
        RunProgress(running=True, stage="running", step=3, total=8, label="1 of 2", stopping=True)
    )
    assert 'data-stage="running" data-step="3" data-total="8" data-label="1 of 2" data-stopping="1"' in body
    assert body.endswith('hx-target="#progress" hx-swap="innerHTML"></div>')
    assert presenter().progress(RunProgress()).startswith("<div hx-get")


def _decoded(reference):
    return Image.open(io.BytesIO(reference.png))


def test_a_rotated_photo_is_turned_upright():
    image = Image.new("RGB", (40, 30), "blue")
    exif = image.getexif()
    exif[0x0112] = 6  # the camera was turned: show it rotated 90 degrees
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    reference = run_request(
        {"prompt": "p", "references": json.dumps([base64.b64encode(buffer.getvalue()).decode()])}
    ).references[0]
    assert (reference.width, reference.height) == (30, 40) and _decoded(reference).size == (30, 40)


def test_a_png_is_encoded_again_without_its_text():
    image = Image.new("RGB", (8, 8), "blue")
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", "a secret prompt")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", pnginfo=info)
    reference = run_request(
        {"prompt": "p", "references": json.dumps([base64.b64encode(buffer.getvalue()).decode()])}
    ).references[0]
    assert b"a secret prompt" not in reference.png


@pytest.mark.parametrize("mode, expected", [("CMYK", "RGB"), ("L", "RGB"), ("RGBA", "RGBA"), ("I;16", "RGB")])
def test_every_color_mode_becomes_rgb(mode, expected):
    buffer = io.BytesIO()
    Image.new(mode, (8, 8)).save(buffer, format="TIFF")
    reference = run_request(
        {"prompt": "p", "references": json.dumps([base64.b64encode(buffer.getvalue()).decode()])}
    ).references[0]
    assert _decoded(reference).mode == expected


def test_the_form_carries_the_backend():
    assert run_request({"prompt": "p", "backend": "flux2"}).backend == "flux2"
