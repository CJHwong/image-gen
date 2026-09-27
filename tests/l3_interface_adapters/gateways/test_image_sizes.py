import pytest

from studio.l3_interface_adapters.gateways.image_sizes import match_reference_size


def test_a_wide_reference_keeps_its_shape_at_about_one_megapixel():
    # mflux resizes the reference to the target size with a plain resize, so a
    # square output from a 16:9 photo would squash it. 1600 x 900 is the shape
    # the edit path is measured on.
    assert match_reference_size(1600, 900) == (1360, 768)


def test_a_standard_camera_size_keeps_its_shape():
    assert match_reference_size(640, 480) == (1184, 880)


def test_a_square_reference_stays_square():
    assert match_reference_size(1024, 1024) == (1024, 1024)


def test_every_size_lands_on_the_16_pixel_grid():
    # mflux needs both sides on the 16 grid. An off-grid side is a refused run,
    # not a rounded one.
    for width, height in [(1600, 900), (640, 480), (3, 1), (1920, 1080)]:
        assert all(side % 16 == 0 for side in match_reference_size(width, height))


def test_a_very_thin_reference_keeps_a_floor_of_one_tile():
    # A 10000 x 1 strip scales its short side under one pixel. The floor keeps
    # the output renderable instead of collapsing it.
    assert match_reference_size(10000, 1) == (102400, 16)


def test_the_area_lands_within_a_few_percent_of_the_budget():
    # The 16 grid moves a side, so the area comes near the budget, not on it.
    width, height = match_reference_size(1600, 900)
    assert width * height == pytest.approx(1024 * 1024, rel=0.03)


def test_a_caller_can_ask_for_another_budget():
    width, height = match_reference_size(1600, 900, 512 * 512)
    assert width * height == pytest.approx(512 * 512, rel=0.03)
    assert width / height == pytest.approx(1600 / 900, rel=0.01)
