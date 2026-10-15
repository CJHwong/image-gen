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
        assert mode.estimate is None


def test_official_turbo_keeps_reference_edit_support():
    capabilities = qwen21_turbo_capabilities()

    assert capabilities.mode("generate").max_references == 1
    assert (capabilities.mode("edit").min_references, capabilities.mode("edit").max_references) == (1, 1)
