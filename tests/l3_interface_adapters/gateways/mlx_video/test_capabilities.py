import pytest

from studio.l3_interface_adapters.gateways.mlx_video.capabilities import (
    ltx23_mlx_capabilities,
    ltx25_mlx_capabilities,
)
from studio.l3_interface_adapters.gateways.prompt_aids import VIDEO_LOOKS, VIDEO_TEMPLATES


@pytest.mark.parametrize(
    ("build", "backend_id", "name"),
    [
        (ltx25_mlx_capabilities, "ltx25_mlx", "LTX-2.5 q8"),
        (ltx23_mlx_capabilities, "ltx23_mlx", "LTX-2.3 q8"),
    ],
)
def test_each_pack_offers_the_same_generic_form(build, backend_id, name):
    """A person sees one Generate form on either pack. The model id changes the weights and
    nothing a control depends on, because every difference lives in the runner."""
    capabilities = build()

    assert capabilities.backend_id == backend_id
    assert capabilities.name == name
    assert capabilities.precision == "int8"
    assert [mode.id for mode in capabilities.modes] == ["generate"]
    assert capabilities.modes[0].accepts_audio is True
    assert capabilities.modes[0].looks == VIDEO_LOOKS
    assert capabilities.templates == VIDEO_TEMPLATES
    assert capabilities.adapters == ()


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
        # the model's 720. The form prints the pixels it will use under the field.


@pytest.mark.parametrize("build", [ltx25_mlx_capabilities, ltx23_mlx_capabilities])
def test_the_frame_controls_sit_on_the_port_s_grid(build):
    capabilities = build()

    assert capabilities.min_frames % capabilities.frame_step == 1
    assert capabilities.max_frames % capabilities.frame_step == 1
    for frames in capabilities.duration_presets:
        assert (frames - 1) % capabilities.frame_step == 0
        assert capabilities.min_frames <= frames <= capabilities.max_frames
    assert capabilities.default_frames in capabilities.duration_presets
