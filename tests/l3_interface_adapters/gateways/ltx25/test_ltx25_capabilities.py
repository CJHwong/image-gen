from studio.l3_interface_adapters.gateways.ltx25.capabilities import ltx25_capabilities


def test_ltx25_shapes_fit_the_two_stage_pipeline_grid():
    capabilities = ltx25_capabilities()

    assert capabilities.default_shape_ratio == "16:9"
    assert capabilities.dimension_step == 64
    assert [(shape.ratio, shape.width, shape.height) for shape in capabilities.shapes] == [
        ("16:9", 1024, 576),
        ("9:16", 576, 1024),
        ("1:1", 768, 768),
    ]
    assert all(dimension % 64 == 0 for shape in capabilities.shapes for dimension in (shape.width, shape.height))


def test_ltx25_duration_choices_belong_to_its_capabilities():
    capabilities = ltx25_capabilities()

    assert capabilities.duration_presets == (121, 241, 361)
    assert (capabilities.min_seed, capabilities.max_seed) == (0, 2**32 - 1)
    assert (
        capabilities.min_reference_strength,
        capabilities.max_reference_strength,
        capabilities.reference_strength_step,
        capabilities.default_reference_strength,
    ) == (0.05, 1.0, 0.05, 1.0)
