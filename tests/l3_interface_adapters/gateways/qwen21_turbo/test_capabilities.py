from studio.l3_interface_adapters.gateways.qwen21_turbo.capabilities import qwen21_turbo_capabilities


def test_official_turbo_has_its_own_name_and_stays_at_eight_steps():
    capabilities = qwen21_turbo_capabilities()
    steps = next(param for param in capabilities.mode("generate").params if param.id == "steps")

    assert capabilities.backend_id == "qwen21_turbo"
    assert capabilities.name == "Qwen-Image-2.1-Turbo"
    assert (steps.default, steps.minimum, steps.maximum) == (8, 8, 8)


def test_official_turbo_does_not_inherit_untested_prompt_aids_or_guidance():
    capabilities = qwen21_turbo_capabilities()

    for mode_id in ("generate", "edit"):
        mode = capabilities.mode(mode_id)
        param_ids = {param.id for param in mode.params}
        assert not mode.looks and not mode.templates
        assert not param_ids & {"guidance", "negative", "cfg"}


def test_official_turbo_has_measured_generate_and_edit_estimates():
    capabilities = qwen21_turbo_capabilities()
    generate = capabilities.mode("generate").estimate
    generate_reference = capabilities.mode("generate").reference_estimate
    edit = capabilities.mode("edit").estimate

    assert generate is not None
    assert (generate.step_cost, generate.exponent, generate.overhead, generate.overhead_per_image) == (
        4.083,
        0.84,
        0,
        True,
    )
    assert generate_reference is not None
    assert (
        generate_reference.step_cost,
        generate_reference.exponent,
        generate_reference.overhead,
        generate_reference.overhead_per_image,
        generate_reference.strength_scales_steps,
    ) == (4.030, 2.066, 2.030, True, True)
    assert edit is not None
    assert (edit.step_cost, edit.exponent, edit.overhead, edit.overhead_per_image, edit.match_cap) == (
        6.514,
        1.22,
        0,
        True,
        1344,
    )


def test_official_turbo_keeps_reference_edit_support():
    capabilities = qwen21_turbo_capabilities()

    assert capabilities.mode("generate").max_references == 1
    assert (capabilities.mode("edit").min_references, capabilities.mode("edit").max_references) == (1, 1)
