import numpy as np

from studio.l3_interface_adapters.gateways.audio.wav_audio import to_wav
from tests.support.voice_audio import read


def test_samples_become_a_16_bit_wav_at_their_rate():
    data = to_wav(np.full(2400, 0.5, dtype=np.float32), 24000)
    samples, rate = read(data)
    assert data[:4] == b"RIFF" and rate == 24000 and len(samples) == 2400
    assert abs(samples[0] - 0.5) < 1e-3
