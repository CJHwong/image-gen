import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l3_interface_adapters.api.prompt_builder import prepare_prompt

MODE = {
    "looks": [
        {
            "name": "Light",
            "options": [("Soft", "Soft window light."), ("Hard", "Direct sunlight.")],
            "avoids": [("Soft", "harsh shadows")],
        }
    ],
    "templates": [{"name": "Portrait", "text": "A portrait of [subject] in [place]."}],
    "params": [{"id": "negative", "default": ""}, {"id": "guidance", "default": 1, "with_negative": 2.5}],
    "each_reference": True,
}


def test_plain_requests_keep_their_values():
    assert prepare_prompt({"prompt": "a pear", "guidance": 1}, MODE) == {"prompt": "a pear", "guidance": 1}


def test_looks_follow_image_punctuation_and_negative_rules():
    result = prepare_prompt({"prompt": "a pear", "looks": {"Light": ["Soft"]}, "negative": "blur"}, MODE)
    assert result == {"prompt": "a pear. Soft window light.", "negative": "blur, harsh shadows", "guidance": 2.5}


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("", "Soft window light."),
        ("a pear!", "a pear! Soft window light."),
        ("a pear。", "a pear。 Soft window light."),
    ],
)
def test_looks_keep_existing_sentence_endings(prompt, expected):
    assert prepare_prompt({"prompt": prompt, "looks": {"Light": "Soft"}}, MODE)["prompt"] == expected


def test_video_looks_append_without_image_punctuation_or_avoids():
    result = prepare_prompt({"prompt": "a pear", "looks": {"Light": "Soft"}}, MODE, video=True)
    assert result == {"prompt": "a pear Soft window light."}


def test_template_fields_compile_from_capabilities():
    result = prepare_prompt(
        {"template": "Portrait", "template_values": {"subject": "a woman", "place": "a garden"}}, MODE
    )
    assert result == {"prompt": "A portrait of a woman in a garden."}


@pytest.mark.parametrize(
    "payload",
    [
        {"looks": []},
        {"looks": {"Unknown": "Soft"}},
        {"looks": {"Light": ["Soft", "Hard"]}},
        {"looks": {"Light": "Unknown"}},
        {"template": "Unknown"},
        {"template": "Portrait"},
        {"template": "Portrait", "template_values": []},
        {"template": "Portrait", "template_values": {"subject": 1, "place": "a room"}},
        {"per_reference_prompts": []},
        {"per_reference_prompts": ["one"]},
        {"per_reference_prompts": [1], "each_reference": True, "references": ["image"]},
    ],
)
def test_invalid_prompt_aids_fail_explicitly(payload):
    with pytest.raises(InvalidJob):
        prepare_prompt(payload, MODE)


def test_per_reference_prompts_keep_master_words_and_looks_last():
    result = prepare_prompt(
        {
            "prompt": "Change the wall",
            "each_reference": True,
            "references": ["first", "second"],
            "per_reference_prompts": ["make it blue", "make it green"],
            "looks": {"Light": "Hard"},
        },
        MODE,
    )
    assert result["per_reference_prompts"] == [
        "Change the wall. make it blue. Direct sunlight.",
        "Change the wall. make it green. Direct sunlight.",
    ]
    assert result["prompt"] == result["per_reference_prompts"][0]


def test_empty_look_selection_adds_nothing():
    assert prepare_prompt({"prompt": "a pear", "looks": {"Light": []}}, MODE) == {"prompt": "a pear"}


def test_invalid_prompt_and_scale_have_explicit_errors():
    with pytest.raises(InvalidJob, match="prompt must"):
        prepare_prompt({"prompt": 1}, MODE)
    with pytest.raises(InvalidJob, match="guidance"):
        prepare_prompt({"prompt": "a pear", "guidance": "bad", "looks": {"Light": "Soft"}}, MODE)


def test_look_avoids_only_apply_to_a_mode_with_negative_input():
    assert prepare_prompt({"looks": {"Light": "Soft"}}, {**MODE, "params": []}) == {"prompt": "Soft window light."}


def test_empty_reference_instruction_keeps_master_and_look():
    result = prepare_prompt(
        {"prompt": "", "references": ["one"], "each_reference": True, "per_reference_prompts": [""]}, MODE
    )
    assert result["prompt"] == ""


@pytest.mark.parametrize("references,mask", [(None, False), (3, False), (["one"], True)])
def test_reference_instructions_refuse_invalid_references_or_masks(references, mask):
    with pytest.raises(InvalidJob):
        prepare_prompt(
            {"references": references, "mask": mask, "each_reference": True, "per_reference_prompts": ["change"]}, MODE
        )


def test_non_scalar_guidance_has_an_explicit_error():
    with pytest.raises(InvalidJob, match="guidance"):
        prepare_prompt({"looks": {"Light": "Soft"}, "guidance": []}, MODE)


def test_instruction_count_must_match_the_references():
    with pytest.raises(InvalidJob, match="one instruction per reference"):
        prepare_prompt(
            {"references": ["one", "two"], "each_reference": True, "per_reference_prompts": ["change"]}, MODE
        )


def test_a_request_with_no_prompt_or_selections_stays_empty():
    assert prepare_prompt({"looks": {}}, MODE) == {}
