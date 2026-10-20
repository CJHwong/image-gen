from studio.l3_interface_adapters.gateways.ltx25.capabilities import ltx25_capabilities
from studio.l3_interface_adapters.gateways.prompt_aids import VIDEO_TEMPLATES


def test_ltx25_offers_the_video_templates_it_was_sampled_on():
    """Four of the eight that were rendered once each at 121 frames, one seed, and judged
    against what each text promises. PROMPTS.md holds the sample and the ones that failed:
    the loop, which did not close, the one action, whose arc never read, and the style
    template, dropped on 2026-10-18 for drawing a frame the clip never asked for. Three more
    shipped on 2026-10-19 from the vendor's guides and the audio references: multi-shot,
    dialogue and soundscape, each rendered once at 121 frames on seed 7."""
    capabilities = ltx25_capabilities()

    assert capabilities.templates == VIDEO_TEMPLATES
    assert [template.name for template in capabilities.templates] == [
        "Camera move",
        "First frame",
        "Last frame",
        "Multi-shot",
        "Dialogue",
        "Soundscape",
        "Product turn",
    ]


def test_ltx25_offers_the_video_look_rows_it_was_sampled_on():
    """Each option ran once beside one bare control clip on 2026-10-19, at 384 x 384 and
    121 frames on seed 7. PROMPTS.md holds the numbers. The text of a Look is appended
    after the prompt, so it can only name what composes with any prompt."""
    generate = ltx25_capabilities().mode("generate")

    assert [(row.name, [label for label, _ in row.options]) for row in generate.looks] == [
        ("Light", ["Golden hour", "Soft daylight", "Neon night"]),
        ("Atmosphere", ["Wet street", "Fog"]),
        ("Grade", ["Warm", "Cool"]),
        ("Mix", ["No music"]),
    ]
    assert ltx25_capabilities().mode("edit").looks == ()


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


def test_ltx25_offers_a_generate_mode_and_an_edit_mode_that_needs_a_clip():
    modes = ltx25_capabilities().modes

    assert [(mode.id, mode.needs_clip) for mode in modes] == [("generate", False), ("edit", True)]


def test_the_day_to_night_adapter_keeps_stage_two_conditioned():
    """Measured on the office M5 Pro, one daylight clip of 97 frames at 768 x 448, seed 7.
    Two stages with stage 2 bare: the frame darkens 107.2 to 39.2, the buildings and street
    hold, and the market stall is replaced by a parked car. Two stages with stage 2 carrying
    the adapter and the reference: the stall, its umbrella and the street furniture all
    survive. So the flag is the adapter's, and so is the prompt the card recommends, which
    the page seeds because nobody can guess it."""
    capabilities = ltx25_capabilities()
    adapter = _adapter(capabilities, "day-to-night")

    assert capabilities.adapters_for("generate") == ()
    assert adapter.file == "ltx-2.5-22b-ic-lora-day-to-night-0.9.safetensors"
    assert adapter.stage_2_conditioning is True
    assert adapter.strength == 1.0
    assert "Only the lighting changes" in adapter.prompt
    assert "night" in adapter.prompt


def test_every_declared_adapter_ran_on_a_clip_that_holds_its_precondition():
    """The set on 2026-10-19, judged at frame 40 against each one's own input. The two that
    need a defective input were re-run on one: soft.mp4 blurred at radius 6, crushed.mp4
    encoded at 150 kbps. Colorize is absent on purpose, and that is what this list records:
    it added no colour to a desaturated clip, 0.52 mean chroma with the second stage
    conditioned and 2.96 with it bare, against 11.5 for a colour clip. The pixel spatial
    upscaler ran on 2026-10-20 at 384 to 768, and the form asks for that doubled shape when
    it is picked."""
    capabilities = ltx25_capabilities()
    adapters = capabilities.adapters_for("edit")

    assert [one.id for one in adapters] == [
        "day-to-night",
        "water-simulation",
        "clean-plate",
        "deblur",
        "decompression",
        "restore",
        "upscale-2x",
    ]
    for one in adapters:
        assert one.mode == "edit"
        assert one.strength == 1.0
        assert one.stage_2_conditioning is True
        assert one.prompt.strip()
        assert one.hint.strip()
        assert one.file in {
            f"ltx-2.5-22b-ic-lora-{one.id}-0.9.safetensors",
            f"ltx-2.5-22b-ic-lora-{one.id}-1.0.safetensors",
            "ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors",
        }


def test_the_upscaler_is_the_one_adapter_that_doubles_its_output():
    """The card asks for a reference at half the target's linear resolution, so the form has
    to ask for a shape twice the clip's. No other adapter re-renders at a new size."""
    capabilities = ltx25_capabilities()
    doubles = [one.id for one in capabilities.adapters_for("edit") if one.doubles_output]

    assert doubles == ["upscale-2x"]


def test_the_trigger_word_leads_the_prompt_the_card_names():
    """Three of these cards answer to a literal word, and the page seeds the prompt whole, so
    the word has to be the first thing in the box for the model to read it as a trigger."""
    capabilities = ltx25_capabilities()

    for adapter_id, trigger in (
        ("water-simulation", "ADD WATER."),
        ("deblur", "DEBLUR."),
        ("decompression", "ENHANCE QUALITY."),
    ):
        assert _adapter(capabilities, adapter_id).prompt.startswith(trigger)

    # The clean plate card warns against naming the thing to remove, so its prompt is the
    # empty scene and carries no trigger word at all.
    assert not _adapter(capabilities, "clean-plate").prompt.startswith("CLEAN")
    assert "empty" in _adapter(capabilities, "clean-plate").prompt


def _adapter(capabilities, adapter_id):
    return next(one for one in capabilities.adapters_for("edit") if one.id == adapter_id)
