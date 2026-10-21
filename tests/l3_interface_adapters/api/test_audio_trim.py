"""A selection preserves PCM bytes and rejects invalid audio before model work."""

import base64
import io
import wave

import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l3_interface_adapters.api.audio_trim import trim_audio


def recording(channels=2, width=2, rate=8, frames=16):
    samples = bytes(index % 256 for index in range(channels * width * frames))
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setparams((channels, width, rate, frames, "NONE", "not compressed"))
        stream.writeframes(samples)
    return output.getvalue(), samples


def payload(raw=None, start=0.25, end=1.25):
    raw = recording()[0] if raw is None else raw
    return {
        "audio": {"name": "selection.wav", "data": base64.b64encode(raw).decode()},
        "start_seconds": start,
        "end_seconds": end,
    }


@pytest.mark.parametrize("channels,width", [(1, 1), (2, 2), (2, 3), (1, 4)])
def test_selection_keeps_original_pcm_samples_and_format(channels, width):
    raw, samples = recording(channels, width)
    selected, duration = trim_audio(payload(raw))
    with wave.open(io.BytesIO(selected), "rb") as stream:
        assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()) == (
            channels,
            width,
            8,
            8,
        )
        assert stream.readframes(8) == samples[2 * channels * width : 10 * channels * width]
    assert duration == 1


def test_whole_clip_and_sample_rounding():
    raw, samples = recording()
    selected, duration = trim_audio(payload(raw, 0, 2))
    assert selected == raw and duration == 2
    selected, duration = trim_audio(payload(raw, 0.19, 0.69))
    with wave.open(io.BytesIO(selected), "rb") as stream:
        assert stream.readframes(99) == samples[2 * 4 : 6 * 4]
    assert duration == 0.5


@pytest.mark.parametrize(
    "start,end",
    [
        (-1, 1),
        (0, 3),
        (1, 1),
        (1, 0.5),
        (True, 1),
        (0, False),
        ("0", 1),
        (None, 1),
        (float("nan"), 1),
        (0, float("inf")),
        (0, -float("inf")),
        (10**400, 1),
        (0, 0.001),
    ],
)
def test_invalid_or_empty_range_is_rejected(start, end):
    with pytest.raises(InvalidJob):
        trim_audio(payload(start=start, end=end))


@pytest.mark.parametrize("audio", [None, [], {}, {"data": 4}, {"data": "???"}, {"data": "data:audio/wav;base64,AAAA"}])
def test_invalid_audio_envelope_is_rejected(audio):
    body = payload()
    body["audio"] = audio
    with pytest.raises(InvalidJob):
        trim_audio(body)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not audio",
        b"RIFF\x00\x00\x00\x00WAVE",
        recording()[0][:-1],
        recording(frames=0)[0],
        recording(rate=1, frames=121)[0],
    ],
)
def test_corrupt_truncated_empty_or_long_recording_is_rejected(raw):
    with pytest.raises(InvalidJob):
        trim_audio(payload(raw))


def test_both_encoded_and_decoded_size_limits(monkeypatch):
    import studio.l3_interface_adapters.api.audio_trim as module

    monkeypatch.setattr(module, "MAX_AUDIO_BYTES", 8)
    with pytest.raises(InvalidJob):
        trim_audio(payload(b"0" * 20))
    with pytest.raises(InvalidJob):
        trim_audio(payload(b"0" * 9))


def test_zero_sample_rate_is_rejected():
    raw = bytearray(recording()[0])
    raw[24:28] = bytes(4)
    with pytest.raises(InvalidJob):
        trim_audio(payload(bytes(raw)))


def test_unsupported_pcm_width_is_rejected():
    raw = bytearray(recording()[0])
    raw[34:36] = (40).to_bytes(2, "little")
    with pytest.raises(InvalidJob):
        trim_audio(payload(bytes(raw)))
