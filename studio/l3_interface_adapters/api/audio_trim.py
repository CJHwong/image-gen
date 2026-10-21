"""Cut a WAV selection without a model or a change to its PCM samples."""

import base64
import binascii
import io
import struct
import wave
from collections.abc import Mapping
from typing import Any

from studio.l1_entities.errors import InvalidJob

MAX_AUDIO_BYTES = 32 * 1024 * 1024
MAX_SECONDS = 120


def trim_audio(payload: Mapping[str, Any]) -> tuple[bytes, float]:
    audio = payload.get("audio")
    if not isinstance(audio, Mapping) or not isinstance(audio.get("data"), str):
        raise InvalidJob("audio must contain bare base64 WAV data")
    encoded = audio["data"]
    if len(encoded) > MAX_AUDIO_BYTES * 4 // 3 + 4:
        raise InvalidJob("The audio exceeds 32 MiB.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise InvalidJob("audio.data must contain bare base64 WAV data") from None
    if len(raw) > MAX_AUDIO_BYTES:
        raise InvalidJob("The audio exceeds 32 MiB.")
    start = _seconds(payload.get("start_seconds"), "start_seconds")
    end = _seconds(payload.get("end_seconds"), "end_seconds")
    try:
        return _cut(raw, start, end)
    except (wave.Error, EOFError, struct.error):
        raise InvalidJob("The audio must contain a complete uncompressed PCM WAV file.") from None


def _seconds(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= MAX_SECONDS:
        raise InvalidJob(f"{name} must be a finite number from 0 to 120.")
    return float(value)


def _cut(raw: bytes, start: float, end: float) -> tuple[bytes, float]:
    with wave.open(io.BytesIO(raw), "rb") as source:
        channels, width, rate, frames, _, _ = source.getparams()
        if not 1 <= width <= 4:
            raise InvalidJob("The audio must use PCM samples from 1 to 4 bytes wide.")
        if rate <= 0 or not 0 < frames <= MAX_SECONDS * rate:
            raise InvalidJob("The audio must contain at most 120 seconds of PCM samples.")
        if not start < end <= frames / rate:
            raise InvalidJob("The selection must end after its start and within the audio duration.")
        samples = source.readframes(frames)
        if len(samples) != frames * channels * width:
            raise InvalidJob("The audio must contain all declared PCM samples.")
    first = round(start * rate)
    last = min(frames, round(end * rate))
    if first >= last:
        raise InvalidJob("The selection must contain at least one audio sample.")
    output = io.BytesIO()
    with wave.open(output, "wb") as selected:
        selected.setparams((channels, width, rate, last - first, "NONE", "not compressed"))
        selected.writeframes(samples[first * channels * width : last * channels * width])
    return output.getvalue(), (last - first) / rate
