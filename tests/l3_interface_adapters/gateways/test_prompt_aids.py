import pytest

from studio.l3_interface_adapters.gateways.prompt_aids import (
    EDIT_TEMPLATES,
    GENERATE_LOOKS,
    GENERATE_TEMPLATES,
    pick_looks,
    pick_templates,
)


def test_a_pick_keeps_the_shared_order_and_drops_the_rest():
    # A backend offers only the options that passed a test on it, but the page
    # still reads them in the shared order. A reordered row would move a chip the
    # user already learned.
    rows = pick_looks({"Light": ("Studio", "Golden hour"), "Color": ("Vivid",)})
    assert [row.name for row in rows] == ["Color", "Light"]
    assert [name for name, _ in rows[1].options] == ["Golden hour", "Studio"]


def test_a_picked_option_keeps_the_sentence_the_shared_row_gave_it():
    rows = pick_looks({"Light": ("Studio",)})
    shared = {row.name: dict(row.options) for row in GENERATE_LOOKS}
    assert rows[0].options == (("Studio", shared["Light"]["Studio"]),)


def test_a_picked_avoid_part_comes_with_its_option():
    # An avoid part goes to the negative prompt, and only a mode with one carries
    # it. Dropping it here would quietly weaken the option that was tested.
    light, realism = pick_looks({"Realism": ("Real person",), "Light": ("Studio",)})
    assert [name for name, _ in realism.avoids] == ["Real person"]
    assert light.avoids == ()


def test_a_sentence_can_be_replaced_for_a_model_that_reads_it_wrong():
    # flux2 draws text it is given, so a named film stock came out printed on a
    # film frame. The name still matches the shared row; only its words change.
    rows = pick_looks({"Film": ("Black and white",)}, sentences={"Black and white": "Black and white film, grain."})
    assert rows[0].options == (("Black and white", "Black and white film, grain."),)


def test_a_look_row_or_option_that_does_not_exist_is_refused():
    # A typo must not drop an option without a word: the backend would offer less
    # than the test that cleared it.
    with pytest.raises(ValueError, match="Colour"):
        pick_looks({"Colour": ("Vivid",)})
    with pytest.raises(ValueError, match="Sepia"):
        pick_looks({"Color": ("Sepia",)})


def test_the_templates_come_back_in_the_order_they_were_named():
    names = ("Product shot", "Poster with text")
    picked = pick_templates(names)
    assert [template.name for template in picked] == list(names)
    shared = {template.name: template for template in GENERATE_TEMPLATES}
    assert picked[0] == shared["Product shot"]


def test_an_edit_template_is_picked_from_the_same_list():
    # The page names a template, and the backend answers whether it is a generate
    # one or an edit one.
    shared = {template.name: template for template in EDIT_TEMPLATES}
    assert pick_templates(("Change a color or material",)) == (shared["Change a color or material"],)


def test_a_template_that_does_not_exist_is_refused():
    with pytest.raises(ValueError, match="Poster"):
        pick_templates(("Poster",))
