"""WAV clips built in memory, so no test reads a fixture from disk."""

import base64
import io

import numpy as np
import soundfile


def wav(seconds: float = 0.5, rate: int = 16000, channels: int = 1) -> bytes:
    frames = int(seconds * rate)
    samples = np.zeros((frames, channels) if channels > 1 else frames, dtype=np.float32)
    buffer = io.BytesIO()
    soundfile.write(buffer, samples, rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def wav_b64(seconds: float = 0.5, rate: int = 16000, channels: int = 1) -> str:
    return base64.b64encode(wav(seconds, rate, channels)).decode("ascii")


def read(data: bytes) -> tuple[np.ndarray, int]:
    samples, rate = soundfile.read(io.BytesIO(data), dtype="float32")
    return samples, rate
