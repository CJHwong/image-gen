"""What the page shows for qwen21, and the limits the core checks before a run."""

import re

import pytest

from studio.l3_interface_adapters.gateways.flux2.capabilities import EDIT_TEMPLATES as flux2_edit_templates
from studio.l3_interface_adapters.gateways.flux2.capabilities import LOOKS as flux2_looks
from studio.l3_interface_adapters.gateways.flux2.capabilities import SIZES as flux2_sizes
from studio.l3_interface_adapters.gateways.qwen21.capabilities import SIZES as qwen21_sizes
from studio.l3_interface_adapters.gateways.qwen21.capabilities import qwen21_capabilities


def capabilities():
    return qwen21_capabilities(badge="bf16")


@pytest.mark.parametrize("sizes", [qwen21_sizes, flux2_sizes], ids=["qwen21", "flux2"])
def test_every_size_keeps_its_named_ratio_on_the_16_pixel_grid(sizes):
    """Within 1%, because the largest tier keeps the model's own sizes: 1664 x 928 is not quite 16:9."""
    for label, width, height in (size for size in sizes if isinstance(size, tuple)):
        named = re.search(r"\((\d+):(\d+)\)", label)
        across, down = (int(named[1]), int(named[2])) if named else (1, 1)
        assert width % 16 == 0 and height % 16 == 0, label
        assert abs(width / height - across / down) <= 0.01 * across / down, label


def test_a_negative_prompt_names_the_guidance_it_needs():
    for mode_id, scale_id in (("generate", "guidance"), ("edit", "cfg")):
        params = {param.id: param for param in capabilities().mode(mode_id).params}
        assert "negative" in params
        scale = params[scale_id]
        assert scale.with_negative == 2.5 and scale.maximum == 10, mode_id


def test_the_edit_estimate_carries_the_cap_and_the_reference_growth():
    """The cap bounds a match against a 2560x1440 screenshot, which would otherwise ask
    for about 1920. One more reference multiplies the step cost by 1.175: measured at
    0.59 MP, a second reference took it from 3.77 to 4.43."""
    caps = capabilities()
    generate, edit = caps.mode("generate").estimate, caps.mode("edit").estimate
    assert edit.match_cap == 1344 and generate.match_cap is None
    assert edit.per_reference == 0.175 and generate.per_reference == 0.0
    assert edit.overhead_per_image and generate.overhead_per_image  # every image pays its own encode
    assert not edit.two_pass  # 2.1 is trained guidance-free, so a step is one pass


def test_only_real_person_carries_an_avoid_part():
    looks = capabilities().mode("generate").looks
    avoids = {row.name: dict(row.avoids) for row in looks if row.avoids}
    assert list(avoids) == ["Realism"] and list(avoids["Realism"]) == ["Real person"]
    assert "airbrushed skin" in avoids["Realism"]["Real person"]


def test_qwen21_offers_the_templates_it_passed():
    caps = capabilities()
    generate = [template.name for template in caps.mode("generate").templates]
    edit = [template.name for template in caps.mode("edit").templates]
    assert generate[-2:] == ["Deadpan absurdity", "Banner"] and len(generate) == 7
    assert edit[-2:] == ["Turn into a pose figure", "Mark a region"] and len(edit) == 8


def test_only_a_mode_tested_with_a_region_offers_the_draw_tool():
    """The page hides the draw tool where no run proved the model respects a region."""
    caps = capabilities()
    assert caps.mode("edit").region_marking is True
    assert caps.mode("generate").region_marking is False


def test_the_skeleton_is_a_medium_on_qwen21_only():
    medium = dict(capabilities().mode("generate").looks[0].options)
    assert list(medium)[-1] == "Skeleton" and "anatomical skeleton" in medium["Skeleton"]
    offered = [name for row in flux2_looks for name, _ in row.options]  # flux2 has not been tested with them
    assert "Skeleton" not in offered and not any(t.name.startswith("Turn into") for t in flux2_edit_templates)


def test_the_look_rows_go_style_then_shot_then_subject():
    looks = capabilities().mode("generate").looks
    assert [row.name for row in looks] == [
        "Medium", "Film", "Color", "Light", "Camera", "Room for text", "Realism", "Portrait",
    ]  # fmt: skip
    film = dict(looks[1].options)
    assert list(film) == ["Portra 400", "Fuji 400H", "Ektachrome", "Black and white"]
    # Each film stock lives in the Film row only, so one pick per row keeps two stocks apart.
    for row in looks[:1] + looks[2:]:
        for _, sentence in row.options:
            assert not any(stock in sentence for stock in ("Portra", "Tri-X", "Fuji", "Ektachrome")), row.name
