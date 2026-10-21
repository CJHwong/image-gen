"""Read Voice requests before they reach the shared model slot."""

import base64
import binascii
import io
import secrets
from collections.abc import Mapping
from dataclasses import asdict

import numpy as np
import soundfile

from studio.l1_entities.errors import InvalidJob, UnknownBackend
from studio.l1_entities.voice_job import ReferenceAudio, SpeechJob
from studio.l2_use_cases.run_voice_use_case import RunVoiceUseCase

MAX_AUDIO_BYTES = 32 * 1024 * 1024


class VoiceController:
    def __init__(self, run: RunVoiceUseCase, capabilities, catalog=None, switch=None):
        self._run = run
        self._capabilities = capabilities
        self._catalog = catalog
        self._switch = switch

    def _backend_id(self, payload):
        backend_id = payload.get("backend", self.active_id())
        if not isinstance(backend_id, str) or not backend_id:
            raise InvalidJob("backend must be a nonempty Voice model id")
        return backend_id

    def _selected(self, payload):
        backend_id = self._backend_id(payload)
        return backend_id, self.model_capabilities(backend_id)

    def run(self, payload: Mapping):
        backend_id, capabilities = self._selected(payload)
        return self._run.execute(voice_job(payload, capabilities), backend_id)

    def run_batch(self, payloads, completed, started, cancelled):
        backend_id, capabilities = self._selected(payloads[0])
        jobs = [voice_job(payload, capabilities) for payload in payloads]
        return self._run.execute_batch(jobs, completed, started, backend_id)

    def active_id(self):
        return self._catalog.active_id() if self._catalog is not None else self._capabilities.backend_id

    def backends(self):
        ids = self._catalog.visible_ids() if self._catalog is not None else (self.active_id(),)
        return [{"id": backend_id, "name": self.model_capabilities(backend_id).name} for backend_id in ids]

    def model_capabilities(self, backend_id=""):
        if not isinstance(backend_id, str):
            raise InvalidJob("backend must be a Voice model id")
        backend_id = backend_id or self.active_id()
        if self._catalog is not None:
            return self._catalog.get(backend_id).capabilities()
        if backend_id != self._capabilities.backend_id:
            raise UnknownBackend(f"no voice backend registered as {backend_id}")
        return self._capabilities

    def switch(self, payload):
        backend_id = self._backend_id(payload)
        if self._switch is None:
            self.model_capabilities(backend_id)
            return
        self._switch.execute(backend_id)

    def capabilities(self):
        capabilities = self.model_capabilities()
        return {
            **asdict(capabilities),
            "max_reference_megabytes": 32,
            "max_seconds": capabilities.max_reference_seconds,
            "max_batch_items": capabilities.max_batch,
        }


def voice_job(payload: Mapping, capabilities) -> SpeechJob:
    if payload.get("backend", capabilities.backend_id) != capabilities.backend_id:
        raise InvalidJob(f"backend must be {capabilities.backend_id}")
    mode = capabilities.mode(str(payload.get("mode") or capabilities.default_mode))
    template, fields = _template_fields(payload, mode)
    text = payload.get("text", payload.get("prompt", ""))
    if template is not None and template.target == "text":
        text = template.text.format(**fields)
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        raise InvalidJob("text must contain between 1 and 20000 characters")
    for param in mode.params:
        if param.kind == "text" and param.id in payload and not isinstance(payload[param.id], str):
            raise InvalidJob(f"{param.id} must contain text")
    options = mode.parse_options({key: str(value) for key, value in payload.items() if value is not None})
    if template is not None and template.target == "voice":
        options["voice"] = template.text.format(**fields)
    if mode.id == "design" and not str(options.get("voice", "")).strip():
        raise InvalidJob("Describe the voice to build under voice.")
    references: tuple[ReferenceAudio, ...] = (_reference(payload["reference"]),) if payload.get("reference") else ()
    mode.check_references(len(references))
    if references and references[0].seconds > capabilities.max_reference_seconds:
        raise InvalidJob(
            f"The {capabilities.name} reference must be {capabilities.max_reference_seconds:g} seconds or shorter."
        )
    if template is not None and template.length_by and options.get("seconds", 0) == 0:
        seconds = next(iter(references)).seconds / float(fields[template.length_by])
        specification = next(param for param in mode.params if param.id == "seconds")
        options["seconds"] = specification.parse(str(seconds))
    seed = payload.get("seed")
    if seed is None or seed == "":
        seed = secrets.randbelow(2**32)
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise InvalidJob("seed must be a whole number between 0 and 4294967295")
    return SpeechJob(mode.id, text.strip(), seed, options, references)


def _template_fields(payload, mode):
    if "template" not in payload:
        return None, {}
    template = next((item for item in mode.templates if item.name == payload["template"]), None)
    if template is None:
        raise InvalidJob("Choose an offered Voice template for this mode.")
    values = payload.get("template_values", {})
    if not isinstance(values, Mapping):
        raise InvalidJob("template_values must be an object.")
    unknown = set(values) - {field.id for field in template.fields}
    if unknown:
        raise InvalidJob("Unknown template fields: " + ", ".join(sorted(map(str, unknown))))
    return template, {
        field.id: _template_value(field, values.get(field.id, field.default)) for field in template.fields
    }


def _template_value(field, value):
    if field.kind == "text" and not isinstance(value, str):
        raise InvalidJob(f"{field.id} must contain text.")
    parsed = field.parse(str(value) if value is not None else None)
    if field.kind == "text" and not parsed:
        raise InvalidJob(f"Fill the {field.id} template field.")
    return parsed


def _reference(reference) -> ReferenceAudio:
    if not isinstance(reference, Mapping) or not isinstance(reference.get("wav_base64"), str):
        raise InvalidJob("reference must contain wav_base64")
    encoded = reference["wav_base64"].split(",")[-1]
    if len(encoded) > MAX_AUDIO_BYTES * 4 // 3 + 4:
        raise InvalidJob("The voice reference exceeds 32 MiB.")
    try:
        raw = base64.b64decode(encoded, validate=True)
        if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
            raise ValueError("The reference is not WAV.")
        samples, rate = soundfile.read(io.BytesIO(raw), dtype="float32", always_2d=True)
    except (ValueError, binascii.Error, RuntimeError, soundfile.LibsndfileError):
        raise InvalidJob("The voice reference must contain readable audio.") from None
    seconds = len(samples) / rate
    if not 0 < seconds <= 120 or not np.isfinite(samples).all():
        raise InvalidJob("The voice reference must contain at most 120 seconds of finite audio.")
    output = io.BytesIO()
    soundfile.write(output, samples.mean(axis=1), rate, format="WAV", subtype="PCM_16")
    return ReferenceAudio(output.getvalue(), seconds, rate)
