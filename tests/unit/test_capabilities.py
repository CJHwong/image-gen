import pytest

from studio.l1_entities.capabilities import Capabilities, Choice, ModeSpec, ParamSpec
from studio.l1_entities.errors import InvalidJob, UnsupportedMode

STEPS = ParamSpec(id="steps", kind="number", default=40, minimum=1, maximum=100, integer=True)
GUIDANCE = ParamSpec(id="guidance", kind="number", default=1.0, minimum=0)
SIZE = ParamSpec(
    id="size",
    kind="choice",
    default="1024x1024",
    choices=(Choice("1024x1024", "1024 x 1024"), Choice("512x512", "512 x 512")),
)
NEGATIVE = ParamSpec(id="negative", kind="text", default="")
GENERATE = ModeSpec(id="generate", label="Generate", params=(STEPS, GUIDANCE, SIZE, NEGATIVE), max_references=1)
EDIT = ModeSpec(id="edit", label="Edit", params=(STEPS,), min_references=1, max_references=10)
CAPS = Capabilities(backend_id="fake", name="Fake", badge="bf16", modes=(GENERATE, EDIT), max_batch=4)


def test_blank_values_take_the_defaults():
    assert GENERATE.parse_options({}) == {"steps": 40, "guidance": 1.0, "size": "1024x1024", "negative": ""}


def test_values_are_typed():
    parsed = GENERATE.parse_options({"steps": "8", "guidance": "2.5", "size": "512x512", "negative": " blur "})
    assert parsed == {"steps": 8, "guidance": 2.5, "size": "512x512", "negative": "blur"}


def test_fields_the_mode_does_not_declare_are_ignored():
    assert "guidance" not in EDIT.parse_options({"guidance": "3"})


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("steps", "0", "steps must be between 1 and 100"),
        ("steps", "4.5", "steps must be a whole number"),
        ("guidance", "-1", "guidance must be at least 0"),
        ("guidance", "abc", "guidance must be a number"),
        ("size", "999x999", "size must be one of 1024x1024, 512x512"),
    ],
)
def test_bad_values_are_refused_with_the_rule(field, value, message):
    with pytest.raises(InvalidJob, match=message):
        GENERATE.parse_options({field: value})


def test_reference_count_follows_the_mode():
    EDIT.check_references(1)
    GENERATE.check_references(0)
    with pytest.raises(InvalidJob, match="needs at least 1 reference image"):
        EDIT.check_references(0)
    with pytest.raises(InvalidJob, match="takes at most 1 reference image"):
        GENERATE.check_references(2)


def test_an_undeclared_mode_is_unsupported():
    assert CAPS.mode("edit") is EDIT
    with pytest.raises(UnsupportedMode, match="Fake has no control mode"):
        CAPS.mode("control")


def test_a_marking_mode_needs_room_for_the_mask():
    # The mask is one more reference, so a mode that carries it needs a slot past
    # the picture. One slot would make every marked run a refusal.
    with pytest.raises(ValueError, match="leave room for the mask"):
        ModeSpec(
            id="edit",
            label="Edit",
            params=(STEPS,),
            min_references=1,
            max_references=1,
            region_marking=True,
        )


def test_a_marking_mode_with_room_is_built():
    mode = ModeSpec(
        id="edit",
        label="Edit",
        params=(STEPS,),
        min_references=1,
        max_references=2,
        region_marking=True,
    )
    assert mode.region_marking and mode.max_references == 2
