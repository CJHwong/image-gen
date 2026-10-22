"""Samples to WAV bytes, in memory. Nothing here touches the disk."""

import io

import numpy as np
import soundfile


def to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    soundfile.write(buffer, samples, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()
