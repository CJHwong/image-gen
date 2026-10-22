"""What the page shows for the official Turbo checkpoint.

The checkpoint offers the same controls as Qwen-Image-2.1, because it drives the
same engines on the same form. The difference is the three things its own weights
decide: its identity, the step count its sigma table has, and the cost fits. The
tests below hold both halves of that: what must match, and what must not.
"""

import pytest

from studio.l3_interface_adapters.gateways.image.qwen21.capabilities import qwen21_capabilities
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.capabilities import qwen21_turbo_capabilities
from studio.l3_interface_adapters.gateways.image.shared.qwen21_turbo_schedule import STEPS as SCHEDULE_STEPS


def turbo():
    return qwen21_turbo_capabilities()


def steps_of(capabilities, mode_id="generate"):
    return next(param for param in capabilities.mode(mode_id).params if param.id == "steps")


def test_official_turbo_has_its_own_name_and_the_schedules_step_count():
    capabilities = turbo()
    steps = steps_of(capabilities)

    assert capabilities.backend_id == "qwen21_turbo"
    assert capabilities.name == "Qwen-Image-2.1-Turbo"
    # Eight, because the checkpoint's table has eight nodes and the engine accepts
    # no other count. Read from the schedule rather than typed, so the two cannot drift.
    assert SCHEDULE_STEPS == 8
    assert (steps.default, steps.minimum, steps.maximum) == (SCHEDULE_STEPS,) * 3


def test_official_turbo_offers_the_same_controls_as_qwen21():
    """The whole record, apart from the step count and the fits.

    This is the executable form of that decision: every control, every Look, every
    template and every limit is the base model's, and only the numbers are this
    checkpoint's own.
    """
    ours, base = turbo(), qwen21_capabilities("bf16")

    assert ours.max_batch == base.max_batch
    for mode_id in ("generate", "edit"):
        our_mode, base_mode = ours.mode(mode_id), base.mode(mode_id)
        assert our_mode.id == base_mode.id
        assert our_mode.label == base_mode.label
        assert our_mode.prompt_hint == base_mode.prompt_hint
        assert our_mode.prompt_required == base_mode.prompt_required
        assert our_mode.looks == base_mode.looks
        assert our_mode.templates == base_mode.templates
        assert (our_mode.min_references, our_mode.max_references) == (
            base_mode.min_references,
            base_mode.max_references,
        )
        assert our_mode.region_marking == base_mode.region_marking
        assert our_mode.each_reference == base_mode.each_reference
        # Every param except the step count, which the schedule decides.
        assert [param for param in our_mode.params if param.id != "steps"] == [
            param for param in base_mode.params if param.id != "steps"
        ]


def test_official_turbo_declares_guidance_and_a_negative_prompt():
    """Measured 2026-10-16: guidance 2.5 changes the picture and takes 2.27x the
    time, and a negative at guidance 1 gives a byte-identical image, which is what
    mflux's own comment claims. The control is live on this checkpoint."""
    for mode_id, scale_id in (("generate", "guidance"), ("edit", "cfg")):
        params = {param.id: param for param in turbo().mode(mode_id).params}
        assert "negative" in params
        assert params[scale_id].with_negative == 2.5 and params[scale_id].maximum == 10


def test_official_turbo_has_measured_generate_and_edit_estimates():
    generate = turbo().mode("generate").estimate
    generate_reference = turbo().mode("generate").reference_estimate
    edit = turbo().mode("edit").estimate

    assert generate is not None
    assert (generate.step_cost, generate.exponent, generate.overhead, generate.overhead_per_image) == (
        2.429,
        1.173,
        5.4,
        True,
    )
    assert generate_reference is not None
    assert (
        generate_reference.step_cost,
        generate_reference.exponent,
        generate_reference.overhead,
        generate_reference.overhead_per_image,
        generate_reference.strength_scales_steps,
    ) == (2.679, 1.097, 5.4, True, True)
    assert edit is not None
    assert (edit.step_cost, edit.exponent, edit.overhead, edit.overhead_per_image, edit.match_cap) == (
        3.463,
        1.234,
        21.9,
        True,
        1344,
    )
    assert edit.per_reference == 0.447


def test_the_edit_estimate_follows_the_references_it_is_given():
    """Ten references cost 94.4s at 0.59 MP against 31.3s for one, so the fit has to
    grow with the count. Its own reading of the growth is deliberately high: the step
    cost only rises 2.13x, and the encodes have nowhere else to go.

    Both ends are checked against the measured seconds, so this fails if a future
    number stops describing the runs it came from.
    """
    edit = turbo().mode("edit").estimate
    one = edit.step_cost * 0.59**edit.exponent * 8 + edit.overhead
    ten = edit.step_cost * (1 + edit.per_reference * 9) * 0.59**edit.exponent * 8 + edit.overhead

    assert one == pytest.approx(31.3, rel=0.20)  # measured 31.33s, this errs high
    assert one > 31.3
    assert ten == pytest.approx(94.4, rel=0.02)  # measured 94.41s


def test_official_turbo_keeps_the_base_models_reference_edit_support():
    generate = turbo().mode("generate")
    edit = turbo().mode("edit")

    assert generate.max_references == 1  # mflux's generate_image takes one image_path
    assert (edit.min_references, edit.max_references) == (1, 10)
