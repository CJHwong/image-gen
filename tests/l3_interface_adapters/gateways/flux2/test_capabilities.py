import pytest

from studio.l3_interface_adapters.gateways.flux2.capabilities import MAX_BATCH, SIZES, flux2_capabilities


@pytest.fixture
def caps():
    return flux2_capabilities("int8")


def test_the_page_sees_the_backend_and_its_two_modes(caps):
    assert (caps.backend_id, caps.name, caps.badge, caps.max_batch) == ("flux2", "FLUX.2 klein 9B", "int8", MAX_BATCH)
    assert [mode.id for mode in caps.modes] == ["generate", "edit"]


def test_the_page_sees_no_negative_prompt(caps):
    # This backend declares no negative prompt, so the page offers no field for
    # one. A stray knob would render a control the engine drops.
    for mode in caps.modes:
        assert "negative" not in [param.id for param in mode.params]


def test_an_edit_sizes_itself_from_the_reference_and_a_generate_does_not(caps):
    assert [param.default for param in caps.mode("edit").params if param.id == "size"] == ["match"]
    assert [param.default for param in caps.mode("generate").params if param.id == "size"] == ["1024x1024"]


def test_the_estimate_says_it_was_measured_with_two_passes(caps):
    # Measured at guidance 4, and guidance above 1 runs the model twice. An
    # estimate without this halves the time the page shows.
    assert all(mode.estimate.two_pass for mode in caps.modes)


def test_only_generate_offers_a_starting_image(caps):
    # Flux2Klein.generate_image takes one image_path and no strength limit of
    # its own; the edit mode is where several references go.
    assert caps.mode("generate").max_references == 1
    assert caps.mode("edit").min_references == 1
    assert caps.mode("edit").max_references == 4  # measured: 9.71 s/step against 3.63 with one


def test_flux2_offers_only_the_prompt_aids_it_passed(caps):
    generate, edit = caps.modes
    offered = {row.name: [name for name, _ in row.options] for row in generate.looks}
    assert offered == {
        "Medium": ["Watercolor", "3D render"],
        "Film": ["Portra 400", "Black and white"],
        "Color": ["Vivid"],
        "Light": ["Studio", "Night with neon"],
        "Camera": ["Wide 24mm", "Top-down"],
        "Room for text": ["Left", "Top"],
    }
    black_and_white = dict(generate.looks[1].options)["Black and white"]
    assert "Kodak" not in black_and_white  # flux2 prints a named film stock on the frame
    assert [template.name for template in generate.templates] == [
        "Portrait photo",
        "Product shot",
        "Landscape",
        "Poster with text",
        "Illustration",
    ]
    assert [template.name for template in edit.templates] == [
        "Change a color or material",
        "Replace the background",
        "Add text",
    ]


def test_every_size_keeps_its_named_ratio_on_the_16_pixel_grid():
    # mflux needs both sides on the 16 grid. The label promises a shape, so the
    # two sides have to agree with it, within the rounding of one grid step.
    for label, width, height in SIZES:
        assert width % 16 == 0 and height % 16 == 0, label
        ratio, _, shape = label.partition(" (")
        named_width, named_height = (int(side) for side in ratio.split(" x "))
        if not shape:
            assert width == named_width and height == named_height, label
            continue
        assert width / height == pytest.approx(named_width / named_height, rel=0.01), label
