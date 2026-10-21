import base64

import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l3_interface_adapters.gateways.auk_voice.capabilities import auk_capabilities
from tests.support.voice_audio import wav


def voice_job(request):
    from studio.l3_interface_adapters.controllers.voice_controller import voice_job as parse

    return parse(request, auk_capabilities("flash"))


def test_design_options_and_reference_decode():
    job = voice_job({"mode": "design", "text": "Hello", "voice": "A warm clear voice", "seed": 7})
    assert job.text == "Hello" and job.options["voice"] == "A warm clear voice"
    clone = voice_job({"mode": "clone", "text": "Hi", "reference": {"wav_base64": base64.b64encode(wav()).decode()}})
    assert clone.references[0].seconds > 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"mode": "design", "text": "Hello"},
        {"mode": "clone", "text": "Hi"},
        {"mode": "design", "text": "Hello", "voice": "warm", "seconds": -1},
        {"mode": "design", "text": "Hello", "voice": "warm", "seconds": float("nan")},
        {"mode": "clone", "text": "Hi", "reference": {"wav_base64": "no!"}},
    ],
)
def test_bad_voice_requests_are_refused(payload):
    with pytest.raises(InvalidJob):
        voice_job(payload)


@pytest.mark.parametrize(
    "extra",
    [
        {"backend": "other"},
        {"seed": True},
        {"seed": -1},
        {"seed": "1"},
        {"reference": "bad"},
        {"reference": {"wav_base64": 1}},
        {"reference": {"wav_base64": base64.b64encode(b"not audio").decode()}},
        {"reference": {"wav_base64": base64.b64encode(wav(seconds=0)).decode()}},
    ],
)
def test_other_invalid_inputs(extra):
    with pytest.raises(InvalidJob):
        voice_job({"mode": "design", "text": "Hello", "voice": "warm", **extra})


def test_oversize_reference_is_refused(monkeypatch):
    import studio.l3_interface_adapters.controllers.voice_controller as module

    monkeypatch.setattr(module, "MAX_AUDIO_BYTES", 1)
    with pytest.raises(InvalidJob, match="32 MiB"):
        voice_job({"mode": "clone", "text": "Hello", "reference": {"wav_base64": base64.b64encode(wav()).decode()}})


def test_reference_nan_samples_are_refused(monkeypatch):
    import numpy as np

    import studio.l3_interface_adapters.controllers.voice_controller as module

    monkeypatch.setattr(module.soundfile, "read", lambda *args, **kwargs: (np.array([[np.nan]]), 16000))
    with pytest.raises(InvalidJob, match="finite audio"):
        voice_job({"mode": "clone", "text": "Hello", "reference": {"wav_base64": base64.b64encode(wav()).decode()}})


def test_controller_maps_single_and_batch_requests():
    from unittest.mock import Mock

    from studio.l3_interface_adapters.controllers.voice_controller import VoiceController

    run = Mock()
    controller = VoiceController(run, auk_capabilities("flash"))
    payload = {"mode": "design", "text": "Hello", "voice": "A warm voice", "seed": 7}
    assert controller.run(payload) == run.execute.return_value
    assert run.execute.call_args.args[0].seed == 7
    completed, started, cancelled = Mock(), Mock(), Mock()
    assert controller.run_batch([payload], completed, started, cancelled) == run.execute_batch.return_value
    assert controller.capabilities()["max_batch_items"] == 16
    assert controller.capabilities()["max_batch"] == controller.capabilities()["max_batch_items"]
    assert controller.capabilities()["loading"]["policy"] == "download_on_first_use"


@pytest.mark.parametrize("seconds, expected", [(0, 4), (2, 2)])
def test_speed_template_uses_actual_reference_length_unless_duration_is_explicit(seconds, expected):
    payload = {
        "mode": "edit",
        "template": "Speed",
        "seconds": seconds,
        "reference": {"wav_base64": base64.b64encode(wav(seconds=6)).decode()},
    }
    job = voice_job(payload)
    assert job.text == "Adjust the speech speed to 1.5x."
    assert job.options["seconds"] == expected


def test_voice_template_checks_fields_and_compiles_the_instruction():
    job = voice_job(
        {
            "mode": "edit",
            "template": "Replace words",
            "template_values": {"original": "blue", "new": "green"},
            "reference": {"wav_base64": base64.b64encode(wav()).decode()},
        }
    )
    assert job.text == "Replace 'blue' with 'green'."
    assert job.options["seconds"] == 0


@pytest.mark.parametrize(
    "extra",
    [
        {"template": "missing"},
        {"template": "Speed", "template_values": []},
        {"template": "Speed", "template_values": {"speed": "0"}},
        {"template": "Speed", "template_values": {"typo": "1.5"}},
        {"template": "Replace words", "template_values": {"original": "blue"}},
        {"template": "Replace words", "template_values": {"original": "", "new": "green"}},
        {"template": "Replace words", "template_values": {"original": 4, "new": "green"}},
        {"template": "Pitch", "template_values": {"semitones": "bad"}},
        {"mode": "clone", "template": "Speed"},
    ],
)
def test_invalid_voice_templates_are_refused(extra):
    with pytest.raises(InvalidJob):
        voice_job({"mode": "edit", "reference": {"wav_base64": base64.b64encode(wav()).decode()}, **extra})


def test_speed_template_cannot_exceed_the_output_duration_limit():
    with pytest.raises(InvalidJob, match="120"):
        voice_job(
            {
                "mode": "edit",
                "template": "Speed",
                "template_values": {"speed": "0.5"},
                "reference": {"wav_base64": base64.b64encode(wav(seconds=80)).decode()},
            }
        )


def test_controller_rejects_nontext_or_unknown_models_without_loading():
    from unittest.mock import Mock

    from studio.l1_entities.errors import UnknownBackend
    from studio.l3_interface_adapters.controllers.voice_controller import VoiceController

    controller = VoiceController(Mock(), auk_capabilities("flash"))
    with pytest.raises(InvalidJob, match="Voice model id"):
        controller.run({"backend": 3})
    with pytest.raises(UnknownBackend):
        controller.model_capabilities("missing")
    controller.switch({"backend": "auk"})
    with pytest.raises(UnknownBackend):
        controller.switch({"backend": "missing"})


@pytest.mark.parametrize("backend", [[], {}, True, None, ""])
def test_voice_controller_rejects_invalid_model_types(backend):
    from unittest.mock import Mock

    from studio.l3_interface_adapters.controllers.voice_controller import VoiceController

    controller = VoiceController(Mock(), auk_capabilities("flash"))
    with pytest.raises(InvalidJob):
        controller.run({"backend": backend})
    with pytest.raises(InvalidJob):
        controller.switch({"backend": backend})
    if not isinstance(backend, str):
        with pytest.raises(InvalidJob):
            controller.model_capabilities(backend)


@pytest.mark.parametrize("variant", ["flash", "base"])
def test_design_templates_build_the_voice_without_replacing_the_script(variant):
    from studio.l3_interface_adapters.controllers.voice_controller import voice_job as parse
    from studio.l3_interface_adapters.gateways.auk_voice.capabilities import DESIGN_TEMPLATES

    caps = auk_capabilities(variant)
    for template in DESIGN_TEMPLATES:
        payload = {"mode": "design", "text": "Keep these spoken words.", "template": template.name, "seed": 7}
        job = parse(payload, caps)
        assert job.text == payload["text"]
        assert job.options["voice"] == template.text.format(**{field.id: field.default for field in template.fields})
        values = {field.id: "chosen " + field.id for field in template.fields}
        custom = parse({**payload, "voice": "ignored raw voice", "template_values": values}, caps)
        assert custom.text == payload["text"]
        assert custom.options["voice"] == template.text.format(**values)


@pytest.mark.parametrize(
    "extra",
    [
        {"text": ""},
        {"text": 1},
        {"template_values": []},
        {"template_values": {"speaker": ""}},
        {"template_values": {"speaker": None}},
        {"template_values": {"speaker": False}},
        {"template_values": {"unknown": "word"}},
    ],
)
def test_design_template_validation_keeps_script_and_field_requirements(extra):
    with pytest.raises(InvalidJob):
        voice_job({"mode": "design", "text": "Hello.", "template": "Voice profile", **extra})


def test_voice_text_parameters_reject_objects_instead_of_stringifying_them():
    with pytest.raises(InvalidJob, match="voice must contain text"):
        voice_job({"text": "Hello", "voice": {"prompt": "warm"}})


def test_backend_default_mode_and_required_reference_transcript():
    from studio.l1_entities.voice_capabilities import Capabilities, ModeSpec, ParamSpec, Template
    from studio.l3_interface_adapters.controllers.voice_controller import voice_job as parse

    generate = ModeSpec(
        "generate",
        "Generate",
        (),
        templates=(
            Template("Whisper", "", "[whispers] {script}", fields=(ParamSpec("script", "text", "A quiet evening."),)),
        ),
    )
    clone = ModeSpec("clone", "Clone", (ParamSpec("ref_text", "text", "", required=True),), 1, 1)
    caps = Capabilities(
        "drama3", "Drama-3", "", (generate, clone), 16, default_mode="generate", reference_sample_rate=44100
    )
    assert parse({"text": "Hello"}, caps).mode == "generate"
    assert parse({"template": "Whisper"}, caps).text == "[whispers] A quiet evening."
    assert parse({"template": "Whisper", "template_values": {"script": "Hello"}}, caps).text == "[whispers] Hello"
    reference = {"wav_base64": base64.b64encode(wav()).decode()}
    for value in (None, "", "  ", {}, 3):
        with pytest.raises(InvalidJob, match="ref_text must contain text"):
            parse({"mode": "clone", "text": "Hello", "reference": reference, "ref_text": value}, caps)
    assert (
        parse(
            {"mode": "clone", "text": "Hello", "reference": reference, "ref_text": "The reference words."}, caps
        ).options["ref_text"]
        == "The reference words."
    )
    with pytest.raises(InvalidJob, match="at most 0"):
        parse({"text": "Hello", "reference": reference}, caps)


def test_drama_reference_limit_is_checked_before_the_engine():
    from studio.l3_interface_adapters.controllers.voice_controller import voice_job as parse
    from studio.l3_interface_adapters.gateways.drama_voice.capabilities import drama_capabilities

    with pytest.raises(InvalidJob, match="15 seconds or shorter"):
        parse(
            {
                "mode": "clone",
                "text": "New words.",
                "ref_text": "The recorded words.",
                "reference": {"wav_base64": base64.b64encode(wav(seconds=16)).decode()},
            },
            drama_capabilities(),
        )
