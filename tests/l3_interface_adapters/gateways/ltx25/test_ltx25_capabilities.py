from studio.l3_interface_adapters.gateways.ltx25.capabilities import ltx25_capabilities
from studio.l3_interface_adapters.gateways.prompt_aids import VIDEO_TEMPLATES


def test_ltx25_offers_the_video_templates_it_was_sampled_on():
    """Four of the eight that were rendered once each at 121 frames, one seed, and judged
    against what each text promises. PROMPTS.md holds the sample and the ones that failed:
    the loop, which did not close, the one action, whose arc never read, and the style
    template, dropped on 2026-10-18 for drawing a frame the clip never asked for."""
    capabilities = ltx25_capabilities()

    assert capabilities.templates == VIDEO_TEMPLATES
    assert [template.name for template in capabilities.templates] == [
        "Camera move",
        "First frame",
        "Last frame",
        "Product turn",
    ]


def test_the_two_keyframe_templates_name_the_reference_image():
    """The page offers a template only while it can be kept, and it reads this phrase to
    decide: a template naming the reference image is left out while the video has none."""
    keyframe = [template for template in ltx25_capabilities().templates if "reference image" in template.text]

    assert [template.name for template in keyframe] == ["First frame", "Last frame"]


def test_no_video_template_asks_for_a_film_look():
    """The style template was dropped on 2026-10-18. Asking a video prompt for a film look
    draws black bands down both sides of the frame, 5.2 to 6.1 on the outer 4% band against a
    bare control's 107.3 and 81.2, and six wordings did not lift it, one of them asking the
    picture to fill the frame. A template that asks for one has to answer that first."""
    look = [template for template in ltx25_capabilities().templates if "film stock" in template.text]

    assert look == []


def test_ltx25_offers_a_low_resolution_ladder_for_every_shape():
    """Every size the model renders, lowest first, so a prompt can be tried before it is
    worth four minutes: 121 frames cost 180 seconds at 640 x 384 against 431 at 1024 x 576,
    measured on the office machine. A side is a multiple of 64, so a low rung cannot hold its
    shape exactly, and the form prints the pixels it will use."""
    capabilities = ltx25_capabilities()
    ladder = [(shape.ratio, shape.width, shape.height) for shape in capabilities.shapes]

    assert ladder == [
        ("1:1", 384, 384),
        ("1:1", 512, 512),
        ("1:1", 768, 768),
        ("16:9", 640, 384),
        ("16:9", 768, 448),
        ("16:9", 1024, 576),
        ("16:9", 1280, 704),
        ("9:16", 384, 640),
        ("9:16", 448, 768),
        ("9:16", 576, 1024),
        ("3:2", 768, 512),
        ("3:2", 960, 640),
        ("3:2", 1152, 768),
        ("2:3", 512, 768),
        ("2:3", 640, 960),
        ("2:3", 768, 1152),
    ]
    for ratio in ("1:1", "16:9", "9:16", "3:2", "2:3"):
        sizes = [shape for shape in capabilities.shapes if shape.ratio == ratio]
        assert sizes == sorted(sizes, key=lambda shape: shape.width * shape.height), ratio

    # The form opens on the lowest rung of the default shape, because the first render is
    # usually a prompt test rather than the finished clip. The shape is the square, which is
    # the one the image form opens on, so a still and the clip made from it agree.
    assert capabilities.default_shape_ratio == "1:1"
    default = [shape for shape in capabilities.shapes if shape.ratio == capabilities.default_shape_ratio]
    assert (default[0].width, default[0].height) == (384, 384)

    assert capabilities.dimension_step == 64
    assert all(dimension % 64 == 0 for shape in capabilities.shapes for dimension in (shape.width, shape.height))
    assert all(
        capabilities.min_dimension <= dimension <= capabilities.max_dimension
        for shape in capabilities.shapes
        for dimension in (shape.width, shape.height)
    )


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
