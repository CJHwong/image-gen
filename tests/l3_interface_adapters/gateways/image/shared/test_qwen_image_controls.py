"""The controls the Qwen-Image-2.1 checkpoints share, and the builders that shape them.

ARCHITECTURE.md requires a mirrored test for a new module, and this is it. The two
capability tests use this module through a backend; this one holds it to its own
contract, so a builder that silently dropped a param, or stopped passing the
estimates through, fails here and not three files away.
"""

import pytest

from studio.l1_entities.capabilities import Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.image.shared.qwen_image_controls import (
    CFG,
    GUIDANCE,
    MATCH,
    MAX_BATCH,
    MAX_REFERENCES,
    NEGATIVE,
    RESOLUTION,
    SIZE,
    STRENGTH,
    edit_estimate,
    edit_mode,
    generate_mode,
    steps_param,
)
from studio.l3_interface_adapters.gateways.prompt_aids import (
    EDIT_TEMPLATES,
    GENERATE_TEMPLATES,
)

STEPS = steps_param(default=8, minimum=8, maximum=8)
ESTIMATE = Estimate(1.0, 1.0, 1.0, overhead_per_image=True)
REFERENCE_ESTIMATE = Estimate(2.0, 1.0, 2.0, overhead_per_image=True, strength_scales_steps=True)


def test_the_match_choice_is_one_word_the_engine_reads():
    """Everything that means "follow the reference" has to compare against the same
    string, because the adapters test it and the page sends it."""
    assert MATCH == "match"
    assert any(choice.value == MATCH for choice in SIZE.choices)
    assert any(choice.value == MATCH for choice in RESOLUTION.choices)


def test_the_shared_limits_are_the_ones_the_engines_accept():
    assert MAX_REFERENCES == 10  # mflux's edit call takes a list
    assert MAX_BATCH == 4


def test_a_negative_prompt_names_the_scale_that_turns_true_cfg_on():
    assert NEGATIVE.kind == "text" and NEGATIVE.default == ""
    for scale in (GUIDANCE, CFG):
        assert scale.with_negative == 2.5 and scale.maximum == 10
        assert scale.kind == "number"


def test_the_strength_control_spans_what_the_engine_skips():
    assert STRENGTH.default == 0.4
    assert (STRENGTH.minimum, STRENGTH.maximum, STRENGTH.step) == (0.05, 1, 0.05)


def test_a_step_param_takes_the_bounds_a_schedule_gives_it():
    """The one control a checkpoint decides for itself, so it is built rather than
    declared: an integer count with the range its own schedule has."""
    steps = steps_param(default=40, minimum=1, maximum=100)

    assert isinstance(steps, ParamSpec)
    assert (steps.id, steps.kind, steps.integer) == ("steps", "number", True)
    assert (steps.default, steps.minimum, steps.maximum) == (40, 1, 100)


def test_a_generate_mode_carries_the_shared_controls_and_both_estimates():
    mode = generate_mode(STEPS, ESTIMATE, REFERENCE_ESTIMATE)

    assert isinstance(mode, ModeSpec)
    assert (mode.id, mode.label) == ("generate", "Generate")
    assert mode.params == (SIZE, STEPS, GUIDANCE, STRENGTH, NEGATIVE)
    # mflux's generate_image takes one image_path, so a generate mode never takes more.
    assert mode.max_references == 1
    assert (mode.estimate, mode.reference_estimate) == (ESTIMATE, REFERENCE_ESTIMATE)
    assert mode.looks and mode.templates


def test_a_generate_mode_survives_a_checkpoint_with_no_reference_fit():
    """Qwen-Image-2.1 has none: it declares no fit for a run that starts from a
    picture, and that is a gap rather than a zero."""
    assert generate_mode(STEPS, ESTIMATE, None).reference_estimate is None


def test_an_edit_mode_carries_the_mark_and_the_reference_limits():
    mode = edit_mode(STEPS, ESTIMATE)

    assert (mode.id, mode.label) == ("edit", "Edit")
    assert mode.params == (RESOLUTION, STEPS, CFG, NEGATIVE)
    assert (mode.min_references, mode.max_references) == (1, MAX_REFERENCES)
    assert mode.region_marking is True
    assert mode.each_reference is True
    assert mode.templates == EDIT_TEMPLATES
    assert mode.looks


def test_an_edit_estimate_pays_an_encode_for_every_reference():
    estimate = edit_estimate(3.0, 1.2, 20.0, 0.5)

    assert (estimate.step_cost, estimate.exponent, estimate.overhead) == (3.0, 1.2, 20.0)
    assert estimate.per_reference == 0.5
    # Each image of a batch is its own run, so each pays its own encode, and the cap
    # bounds a match against a large screenshot.
    assert estimate.overhead_per_image is True
    assert estimate.match_cap == pytest.approx(1344)


def test_the_generate_templates_are_the_shared_catalog():
    """A backend declaring none of its own gets all of them, which is what the
    builders above are for."""
    mode = generate_mode(STEPS, ESTIMATE, None)

    assert mode.templates == GENERATE_TEMPLATES
