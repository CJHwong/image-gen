"""What the server sends the page: the page itself, and the fragments htmx swaps in.

The fragments carry data, not layout, so each test reads the fields the page
receives. The e2e check drives the rendered page; this file does not.
"""

import base64
import html
import json
import re

import pytest

from studio.l1_entities.errors import BackendBusy, Cancelled, InvalidJob, MissingPrompt, ReferenceExpired
from studio.l1_entities.image_job import ImageResult
from studio.l1_entities.run_progress import RunProgress
from studio.l2_use_cases.describe_studio_use_case import StudioView
from studio.l2_use_cases.rewrite_prompt_use_case import RewriteResponse
from studio.l2_use_cases.run_image_use_case import NextRun, RunImageResponse
from studio.l3_interface_adapters.presenters.html_presenter import HtmlPresenter
from tests.support.fakes import fake_capabilities

PAGE = "<title>__NAME__</title><input value=__BACKEND__><b>__BADGE__</b><script>const STUDIO = __STUDIO__;</script>"


def presenter():
    return HtmlPresenter(PAGE)


def studio_data(body):
    """The JSON the page reads out of the script tag, after the browser parses it."""
    found = re.search(r"const STUDIO = (.*);</script>", body)
    assert found
    return json.loads(found.group(1))


def chain_values(body):
    """The values the next image of the batch posts, after the browser reads them."""
    found = re.search(r"hx-vals='([^']*)'", body)
    assert found
    return json.loads(html.unescape(found.group(1)))


def response(next_run=None):
    image = ImageResult(png=b"\x89PNGdata", width=640, height=480, seed=9, steps=8)
    return RunImageResponse(
        image=image, mode="generate", prompt='a "red" apple', position="1 of 2", elapsed=12.4, next_run=next_run
    )


def test_the_page_carries_the_capabilities():
    caps = fake_capabilities(name="Fake </script> engine")
    body = presenter().page(StudioView(active=caps, backends=(("fake", "Fake", "What it is."),)))
    assert "<title>Fake &lt;/script&gt; engine</title>" in body and "<b>bf16</b>" in body
    assert "<input value=fake>" in body  # the form names the backend it was built for
    studio = studio_data(body)
    assert studio["backend"]["max_batch"] == 4 and studio["backends"] == [["fake", "Fake", "What it is."]]
    edit = studio["modes"][1]
    assert edit["id"] == "edit" and edit["min_references"] == 1 and edit["params"][0]["id"] == "steps"
    assert studio["rewrite_modes"] == []


def test_a_name_cannot_end_the_data_script():
    # The JSON sits in a script tag, where "</" would close the tag and drop the rest.
    body = presenter().page(StudioView(active=fake_capabilities(name="Fake </script> engine"), backends=()))
    data = body.split("const STUDIO = ")[1].split(";</script>")[0]
    assert "</script>" not in data and "<\\/" in data
    assert studio_data(body)["backend"]["name"] == "Fake </script> engine"


def test_the_page_is_told_which_modes_a_rewriter_serves():
    # An empty list leaves the page's rewrite toggle out, so the list has to arrive.
    view = StudioView(active=fake_capabilities(), backends=(), rewrite_modes=("generate", "edit"))
    assert studio_data(presenter().page(view))["rewrite_modes"] == ["generate", "edit"]


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
    assert chain_values(body) == {
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


def test_a_late_image_of_a_batch_posts_no_picture_again():
    # The references stay on the server under the token, so a large picture does
    # not travel again for each image of the batch.
    nxt = NextRun(
        mode="generate",
        prompt="p",
        seed=10,
        options={},
        total=2,
        index=2,
        reference_token="tok",
        backend="fake",
    )
    body = presenter().run(response(nxt))
    values = chain_values(body)
    assert "references" not in values and values["reference_token"] == "tok"


def test_the_rewrite_answers_with_the_data_the_page_reads():
    # This fragment is JSON, not HTML: the page puts `prompt` in the box and picks
    # `size` in the menu. So a JSON object is the contract, and the text is not escaped.
    body = HtmlPresenter.rewrite(RewriteResponse(prompt="a 貓 in the rain", size="1024x1024", elapsed=30.44))
    assert json.loads(body) == {"prompt": "a 貓 in the rain", "size": "1024x1024", "elapsed": 30.4}
    assert "貓" in body  # not escaped into \uXXXX, which the page would show as text


def test_a_rewrite_with_no_size_says_so():
    assert json.loads(HtmlPresenter.rewrite(RewriteResponse(prompt="p", size=None, elapsed=1.04)))["size"] is None


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
