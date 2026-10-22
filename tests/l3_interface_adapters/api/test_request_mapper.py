"""JSON input stays compatible with the browser form transport."""

import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l2_use_cases.run_image_use_case import NextRun
from studio.l3_interface_adapters.api.request_mapper import form_value, image_form, next_form, reference_text


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
