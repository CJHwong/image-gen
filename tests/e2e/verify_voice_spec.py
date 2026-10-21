"""Validate Voice schema semantics without a model.

Run: uv run --with jsonschema python tests/e2e/verify_voice_spec.py
"""

import base64
import io
import wave

from jsonschema import Draft202012Validator

from studio.l1_entities.errors import InvalidJob, UnsupportedMode
from studio.l3_interface_adapters.api.openapi import openapi_document
from studio.l3_interface_adapters.controllers.voice_controller import voice_job
from studio.l3_interface_adapters.gateways.auk_voice.capabilities import auk_capabilities
from studio.l3_interface_adapters.gateways.drama_voice.capabilities import drama_capabilities

schema = openapi_document()["components"]["schemas"]["VoiceRequest"]
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema)
buffer = io.BytesIO()
with wave.open(buffer, "wb") as recording:
    recording.setnchannels(1)
    recording.setsampwidth(2)
    recording.setframerate(24000)
    recording.writeframes(b"\0\0" * 24000)
reference = {"wav_base64": base64.b64encode(buffer.getvalue()).decode()}
valid = [
    {"backend": "drama3", "text": "[whispers] Quiet now."},
    {"backend": "drama3", "mode": "generate", "text": "Hello.", "temperature": 0.7},
    {"backend": "drama3", "mode": "clone", "text": "New words.", "reference": reference, "ref_text": "Recorded words."},
    {"backend": "auk", "text": "Hello.", "voice": "A calm narrator with a warm, clear voice."},
    {"backend": "auk_base", "mode": "design", "text": "Hello.", "template": "Narration"},
    {"backend": "auk", "mode": "clone", "text": "Hello.", "reference": reference},
    {"backend": "auk_base", "mode": "edit", "text": "Increase the volume by 5 dB.", "reference": reference},
    # Compatibility is explicit: ignored controls do not acquire an effect.
    {"backend": "drama3", "text": "Hello.", "seconds": 999, "convert": "ignored", "extra_setting": True},
    {
        "backend": "auk",
        "text": "Hello.",
        "voice": "A calm narrator.",
        "temperature": 2,
        "max_tokens": 99999,
        "ref_text": None,
    },
]
for payload in valid:
    validator.validate(payload)
    caps = (
        drama_capabilities()
        if payload["backend"] == "drama3"
        else auk_capabilities("flash" if payload["backend"] == "auk" else "base")
    )
    job = voice_job(payload, caps)
    if payload["backend"] == "drama3":
        assert "seconds" not in job.options and "extra_setting" not in job.options
    else:
        assert "temperature" not in job.options
invalid = [
    {"backend": "auk", "mode": "generate", "text": "Hello."},
    {"backend": "auk_base", "mode": "generate", "text": "Hello."},
    {"backend": "drama3", "mode": "design", "text": "Hello.", "voice": "Warm."},
    {"backend": "drama3", "mode": "edit", "text": "Louder.", "reference": reference},
    {"backend": "drama3", "mode": "clone", "text": "Hello.", "reference": reference},
    {"backend": "drama3", "mode": "clone", "text": "Hello.", "ref_text": "Recorded words."},
    {"backend": "auk", "mode": "clone", "text": "Hello."},
    {"backend": "auk_base", "text": "Hello."},
    {"backend": "drama3", "text": "Hello.", "reference": reference},
    {"backend": "auk", "text": "Hello.", "voice": "Warm.", "reference": reference},
    {"backend": "drama3", "text": "Hello.", "temperature": 2},
    {"backend": "auk", "text": "Hello.", "voice": "Warm.", "seconds": 121},
]
for payload in invalid:
    assert list(validator.iter_errors(payload)), payload
    caps = (
        drama_capabilities()
        if payload["backend"] == "drama3"
        else auk_capabilities("flash" if payload["backend"] == "auk" else "base")
    )
    try:
        voice_job(payload, caps)
    except (InvalidJob, UnsupportedMode):
        pass
    else:
        raise AssertionError("The controller accepted a schema-invalid model request")
for example in openapi_document()["paths"]["/api/v1/voice/generate"]["post"]["requestBody"]["content"][
    "application/json"
]["examples"].values():
    validator.validate(example["value"])
print(
    f"PASS {len(valid)} valid and {len(invalid)} invalid model requests agree between schema and controller; all named Voice examples validate"
)
