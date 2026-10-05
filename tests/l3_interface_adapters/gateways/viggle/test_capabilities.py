"""What Viggle Turbo may offer the page, and what it may not.

The distillation fixes two things: no classifier-free guidance was trained, and
the schedule has six sigma nodes and no others. Both are asserted here, because
both are invisible at runtime until a run comes back wrong.
"""

from studio.l3_interface_adapters.gateways.viggle.capabilities import viggle_turbo_capabilities


def capabilities(badge="bf16"):
    return viggle_turbo_capabilities(badge)


def params(mode_id):
    return {param.id for param in capabilities().mode(mode_id).params}


def test_the_backend_names_itself_in_full():
    """It is not "Turbo": the distilled Qwen-Image-2.1 is the model, and the name
    the picker shows says whose it is."""
    assert capabilities().name == "Viggle Turbo" and capabilities().backend_id == "viggle_turbo"


def test_the_picker_line_says_what_it_is():
    """The picker draws this under the name, so a reader knows what the model is
    before switching to it rather than after."""
    assert capabilities().description == "Viggle's distillation of Qwen-Image-2.1: six steps, no guidance."


def test_six_steps_is_the_only_step_count_offered():
    """mflux's ViggleTurboScheduler raises on any other count before the model
    loads, so a free field here would offer a control whose every other value is
    refused. Both bounds are the same number on purpose."""
    steps = next(param for param in capabilities().mode("generate").params if param.id == "steps")
    assert (steps.default, steps.minimum, steps.maximum) == (6, 6, 6)
    assert params("edit") == {"resolution", "steps"}


def test_the_modes_that_need_guidance_are_not_offered():
    """The student was distilled without CFG, so there is no guidance, no negative
    prompt and no scale to set."""
    for mode_id in ("generate", "edit"):
        assert not params(mode_id) & {"guidance", "negative", "cfg"}


def test_generate_takes_one_reference_and_edit_takes_ten():
    assert capabilities().mode("generate").max_references == 1
    edit = capabilities().mode("edit")
    assert (edit.min_references, edit.max_references) == (1, 10)


def test_nothing_untested_on_this_model_is_offered():
    """ARCHITECTURE.md leaves Looks and templates out until they are tested on the
    model, and nobody has tested them on the distilled schedule. The marked region
    is the same: its bounding power was measured on the 40-step base."""
    for mode_id in ("generate", "edit"):
        mode = capabilities().mode(mode_id)
        assert mode.looks == () and mode.templates == ()
        assert mode.region_marking is False


def test_every_mode_carries_an_estimate_and_a_badge():
    for mode_id in ("generate", "edit"):
        assert capabilities().mode(mode_id).estimate is not None
    assert capabilities("int8").badge == "int8"


def test_an_edit_carries_the_area_budget_and_its_cap():
    """The edit engine sizes from an area, so "match" follows the reference and the
    cap bounds what a large screenshot can ask for."""
    resolution = next(param for param in capabilities().mode("edit").params if param.id == "resolution")
    values = [choice.value for choice in resolution.choices]
    assert resolution.default == "match" and "1024" in values
    assert capabilities().mode("edit").estimate.match_cap is not None
