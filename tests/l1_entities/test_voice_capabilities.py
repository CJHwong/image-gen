import pytest

from studio.l1_entities.errors import InvalidJob, UnsupportedMode
from studio.l1_entities.voice_capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec, Template

SECONDS = ParamSpec(id="seconds", kind="number", default=0, minimum=0, maximum=120, step=0.5)
STEPS = ParamSpec(id="steps", kind="number", default=4, minimum=1, maximum=64, integer=True)
CONVERT = ParamSpec(
    id="convert",
    kind="choice",
    default="tw2s",
    choices=(Choice("tw2s", "Traditional to Simplified"), Choice("off", "As written")),
)
VOICE = ParamSpec(id="voice", kind="text", default="")
CEILING = ParamSpec(id="gain", kind="number", default=1, maximum=4)
FLOOR = ParamSpec(id="rate", kind="number", default=1, minimum=0.5)
DESIGN = ModeSpec(id="design", label="Design", params=(SECONDS, STEPS, CONVERT, VOICE))
CLONE = ModeSpec(id="clone", label="Clone", params=(SECONDS,), min_references=1, max_references=1)
EDIT = ModeSpec(id="edit", label="Edit", params=(), min_references=1, max_references=3)
CAPS = Capabilities(backend_id="fake", name="Fake", badge="int8", modes=(DESIGN, CLONE), max_batch=4)


def test_blank_values_take_the_defaults():
    assert DESIGN.parse_options({}) == {"seconds": 0, "steps": 4, "convert": "tw2s", "voice": ""}


def test_values_are_typed():
    parsed = DESIGN.parse_options({"seconds": "2.5", "steps": "8", "convert": "off", "voice": " calm "})
    assert parsed == {"seconds": 2.5, "steps": 8, "convert": "off", "voice": "calm"}


def test_fields_the_mode_does_not_declare_are_ignored():
    assert CLONE.parse_options({"voice": "calm"}) == {"seconds": 0}


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("seconds", "121", "seconds must be between 0 and 120"),
        ("seconds", "abc", "seconds must be a number"),
        ("steps", "4.5", "steps must be a whole number"),
        ("convert", "s2t", "convert must be one of tw2s, off"),
    ],
)
def test_bad_values_are_refused_with_the_rule(field, value, message):
    with pytest.raises(InvalidJob, match=message):
        DESIGN.parse_options({field: value})


def test_a_one_sided_range_is_checked_on_its_one_side():
    assert CEILING.parse("-9") == -9
    assert FLOOR.parse("99") == 99
    with pytest.raises(InvalidJob, match="gain must be at most 4"):
        CEILING.parse("5")
    with pytest.raises(InvalidJob, match=r"rate must be at least 0\.5"):
        FLOOR.parse("0.1")


def test_reference_count_follows_the_mode():
    CLONE.check_references(1)
    DESIGN.check_references(0)
    with pytest.raises(InvalidJob, match=r"needs at least 1 reference clip$"):
        CLONE.check_references(0)
    with pytest.raises(InvalidJob, match="takes at most 3 reference clips"):
        EDIT.check_references(4)


def test_an_undeclared_mode_is_unsupported():
    assert CAPS.mode("clone") is CLONE
    with pytest.raises(UnsupportedMode, match="Fake has no sing mode"):
        CAPS.mode("sing")


def test_a_mode_carries_its_templates_and_estimate_for_a_client():
    template = Template("Denoise", "", "Remove only the background noise.")
    mode = ModeSpec(id="edit", label="Edit", params=(), templates=(template,), estimate=Estimate(rtf=1.3, overhead=2.0))
    assert mode.templates[0].text == "Remove only the background noise."
    assert mode.estimate == Estimate(rtf=1.3, overhead=2.0)


def test_a_template_carries_its_group_fields_and_length_rule():
    speed = ParamSpec(id="speed", kind="choice", default="1.5", choices=(Choice("1.5", "1.5x"),))
    template = Template(
        "Speed", "", "Adjust the speech speed to {speed}x.", group="Sound", fields=(speed,), length_by="speed"
    )
    assert (template.group, template.fields, template.length_by) == ("Sound", (speed,), "speed")
    assert Template("Denoise", "", "Remove noise.").fields == ()


def test_required_text_and_optional_text_have_distinct_contracts():
    required = ParamSpec("ref_text", "text", "", required=True)
    assert required.parse("  Hello  ") == "Hello"
    for value in (None, "", "  "):
        with pytest.raises(InvalidJob, match="ref_text must contain text"):
            required.parse(value)
    assert VOICE.parse("") == ""


def test_voice_capabilities_describe_native_rate_default_and_template_target():
    assert CAPS.default_mode == "design"
    assert CAPS.reference_sample_rate == 24000
    assert Template("Read", "", "{script}").target == "text"
