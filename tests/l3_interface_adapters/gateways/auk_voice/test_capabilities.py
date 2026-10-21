import re

import pytest

from studio.l3_interface_adapters.gateways.auk_voice.capabilities import EDIT_TEMPLATES, auk_capabilities


def test_flash_and_base_are_two_backends():
    flash, base = auk_capabilities("flash"), auk_capabilities("base")
    assert (flash.backend_id, flash.name, base.backend_id, base.name) == ("auk", "AuK Flash", "auk_base", "AuK")
    fast, slow = flash.mode("clone").estimate, base.mode("clone").estimate
    assert fast is not None and slow is not None and fast.rtf < slow.rtf


def test_loading_policy_names_the_same_pinned_weights_as_the_child():
    from studio.l3_interface_adapters.gateways.auk_voice.auk_child import WEIGHTS_REPO, WEIGHTS_REVISION

    loading = auk_capabilities("flash").loading
    assert loading.policy == "download_on_first_use"
    assert loading.repository == WEIGHTS_REPO
    assert loading.revision == WEIGHTS_REVISION
    assert "first Voice run downloads" in loading.note


def test_the_three_modes_take_the_clips_they_need():
    caps = auk_capabilities("flash")
    assert [(m.id, m.min_references, m.max_references) for m in caps.modes] == [
        ("clone", 1, 1),
        ("design", 0, 0),
        ("edit", 1, 1),
    ]


def test_only_design_takes_a_voice_and_clone_has_no_templates():
    caps = auk_capabilities("flash")
    params = {mode.id: [param.id for param in mode.params] for mode in caps.modes}
    assert params == {
        "clone": ["seconds", "convert"],
        "design": ["voice", "seconds", "convert"],
        "edit": ["seconds", "convert"],
    }
    assert caps.mode("edit").templates == EDIT_TEMPLATES and caps.mode("clone").templates == ()


def test_a_blank_form_asks_the_adapter_to_choose_the_length_and_to_convert():
    assert auk_capabilities("flash").mode("clone").parse_options({}) == {"seconds": 0, "convert": "tw2s"}


def test_the_templates_that_failed_the_test_are_not_offered():
    texts = " ".join(template.text for template in EDIT_TEMPLATES).lower()
    assert "lyric" not in texts and "telephone" not in texts and "first speaker" not in texts


@pytest.mark.parametrize("template", EDIT_TEMPLATES, ids=lambda template: template.name)
def test_every_template_has_a_name_and_an_instruction(template):
    assert template.name and template.text.strip()


GROUPS = ("Words", "Sound", "Voice", "Clean-up")


@pytest.mark.parametrize("template", EDIT_TEMPLATES, ids=lambda template: template.name)
def test_every_template_sits_in_a_group(template):
    assert template.group in GROUPS


@pytest.mark.parametrize("template", EDIT_TEMPLATES, ids=lambda template: template.name)
def test_the_fields_of_a_template_are_the_placeholders_of_its_text(template):
    placeholders = set(re.findall(r"\{(\w+)\}", template.text))
    assert placeholders == {field.id for field in template.fields}


@pytest.mark.parametrize("template", EDIT_TEMPLATES, ids=lambda template: template.name)
def test_a_field_default_is_a_value_the_field_accepts(template):
    for field in template.fields:
        assert field.parse(None) == field.default or field.kind == "text"
        if field.kind == "choice":
            assert field.default in [choice.value for choice in field.choices]


def test_only_speed_scales_the_length_and_it_names_its_field():
    scaled = [template for template in EDIT_TEMPLATES if template.length_by]
    assert [template.name for template in scaled] == ["Speed"]
    assert scaled[0].length_by in [field.id for field in scaled[0].fields]


def test_every_group_has_a_template():
    assert {template.group for template in EDIT_TEMPLATES} == set(GROUPS)


@pytest.mark.parametrize("variant", ["flash", "base"])
def test_design_offers_six_general_templates_with_editable_defaults(variant):
    caps = auk_capabilities(variant)
    templates = caps.mode("design").templates
    assert [template.name for template in templates] == [
        "Voice profile",
        "Conversation",
        "Narration",
        "Commanding delivery",
        "Dramatic character",
        "Emotional delivery",
    ]
    assert next(param for param in caps.mode("design").params if param.id == "voice").default == ""
    for template in templates:
        assert 3 <= len(template.fields) <= 4
        assert set(re.findall(r"\{(\w+)\}", template.text)) == {field.id for field in template.fields}
        assert all(field.kind == "text" and field.default for field in template.fields)
        assert template.text.format(**{field.id: field.default for field in template.fields})
