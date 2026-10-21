import pytest

from studio.l3_interface_adapters.gateways.mlx_video.capabilities import (
    ltx23_mlx_capabilities,
    ltx25_mlx_capabilities,
)
from studio.l3_interface_adapters.gateways.prompt_aids import VIDEO_LOOKS, VIDEO_TEMPLATES


def test_the_2_5_pack_offers_generate_and_the_seven_effects():
    """The q8 port runs the 2.5 effects on its single-stage path, so Edit is offered there."""
    capabilities = ltx25_mlx_capabilities()

    assert capabilities.backend_id == "ltx25_mlx"
    assert capabilities.name == "LTX-2.5"
    assert capabilities.precision == "int8"
    assert [mode.id for mode in capabilities.modes] == ["generate", "edit"]
    assert capabilities.modes[0].accepts_audio is True
    assert capabilities.modes[0].looks == VIDEO_LOOKS
    assert capabilities.templates[: len(VIDEO_TEMPLATES)] == VIDEO_TEMPLATES
    assert [template.name for template in capabilities.templates[len(VIDEO_TEMPLATES) :]] == [
        "Speak to camera",
        "Fixed composition",
        "Slow push-in",
    ]
    assert [adapter.id for adapter in capabilities.adapters] == [
        "day-to-night",
        "water-simulation",
        "clean-plate",
        "deblur",
        "decompression",
        "restore",
        "upscale-2x",
    ]
    assert [one.id for one in capabilities.adapters if one.doubles_output] == ["upscale-2x"]


def test_every_effect_renders_inside_the_model_s_bounds():
    """An effect's card size is the run's size, and the form cannot offer a pair past the
    model's largest side. Clean plate at 1024 x 576 and water at 1280 x 704 both sit inside."""
    capabilities = ltx25_mlx_capabilities()

    for adapter in capabilities.adapters:
        if not adapter.width or not adapter.height:
            continue
        assert capabilities.min_dimension <= adapter.width <= capabilities.max_dimension
        assert capabilities.min_dimension <= adapter.height <= capabilities.max_dimension
        assert adapter.width % 32 == 0 and adapter.height % 32 == 0


def test_the_2_3_pack_offers_generate_only():
    capabilities = ltx23_mlx_capabilities()

    assert capabilities.backend_id == "ltx23_mlx"
    assert capabilities.name == "LTX-2.3"
    assert [mode.id for mode in capabilities.modes] == ["generate"]
    assert capabilities.adapters == ()
    assert capabilities.templates == VIDEO_TEMPLATES


def test_new_camera_templates_keep_the_measured_scene_and_motion():
    import re

    templates = {template.name: template for template in ltx25_mlx_capabilities().templates}
    values = {
        "Subject": "A blue ceramic teapot",
        "surface": "a wooden table",
        "Foreground object": "A red cup",
        "background object": "a green plant",
        "subject name": "the teapot",
        "light": "Soft daylight enters through a window",
        "sound": "quiet room tone",
    }
    scene = (
        "A blue ceramic teapot rests on a wooden table. A red cup stands closer to the camera, "
        "and a green plant stands behind the teapot. Soft daylight enters through a window. "
    )
    endings = {
        "Fixed composition": "The camera stays fixed, holding the same composition. ",
        "Slow push-in": "The camera slowly moves toward the teapot, ending in a closer view while the teapot stays still. ",
    }
    for name, ending in endings.items():
        prompt = re.sub(r"\[([^\]]+)\]", lambda match: values[match[1]], templates[name].text)
        assert prompt == scene + ending + "One continuous shot with quiet room tone."


def test_speech_template_keeps_the_measured_dialogue_and_single_speaker():
    import re

    template = next(item for item in ltx25_mlx_capabilities().templates if item.name == "Speak to camera")
    values = {
        "speaker": "a woman in a blue shirt",
        "background": "a plain gray wall",
        "light": "Soft window light illuminates her face",
        "Subject pronoun": "She",
        "Possessive pronoun": "Her",
        "language": "English",
        "dialogue": "Please bring my blue bag.",
        "sound": "quiet room tone",
    }
    prompt = re.sub(r"\[([^\]]+)\]", lambda match: values[match[1]], template.text)
    assert prompt == (
        "A front-facing medium close-up shows a woman in a blue shirt against a plain gray wall. "
        "Soft window light illuminates her face. She looks into the lens and clearly says in English, "
        '"Please bring my blue bag." Her lips and jaw move naturally with each word. '
        "The camera stays fixed throughout the continuous shot. Her voice is clear over quiet room tone."
    )


@pytest.mark.parametrize("build", [ltx25_mlx_capabilities, ltx23_mlx_capabilities])
def test_every_size_keeps_its_named_ratio_on_the_64_pixel_grid(build):
    capabilities = build()

    assert capabilities.dimension_step == 64
    for shape in capabilities.shapes:
        assert shape.width % 64 == 0 and shape.height % 64 == 0
        assert capabilities.min_dimension <= shape.width <= capabilities.max_dimension
        assert capabilities.min_dimension <= shape.height <= capabilities.max_dimension
        # The ladder is the model's own: 640 x 384 is the wide shape at five to three, and
        # 1280 x 704 sits 2.3 percent off 16:9 because 704 is the tallest 64 pixel side under
        # the model's 720. The 1080 class is 1920 x 1088, which is 0.7 percent off. The form
        # prints the pixels it will use under the field.


@pytest.mark.parametrize("build", [ltx25_mlx_capabilities, ltx23_mlx_capabilities])
def test_the_frame_controls_sit_on_the_port_s_grid(build):
    capabilities = build()

    assert capabilities.min_frames % capabilities.frame_step == 1
    assert capabilities.max_frames % capabilities.frame_step == 1
    for frames in capabilities.duration_presets:
        assert (frames - 1) % capabilities.frame_step == 0
        assert capabilities.min_frames <= frames <= capabilities.max_frames
    assert capabilities.default_frames in capabilities.duration_presets
