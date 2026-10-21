import io
import wave
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.voice_job import SpeechJob
from studio.l3_interface_adapters.gateways.stub_voice_backend_gateway import StubVoiceBackendGateway


@pytest.mark.parametrize("seconds,expected", [(0, 1.0), (0.25, 0.25)])
def test_stub_returns_playable_wav_and_all_progress_steps(monkeypatch, seconds, expected):
    monkeypatch.setattr(
        "studio.l3_interface_adapters.gateways.stub_voice_backend_gateway.time.sleep", lambda duration: None
    )
    backend = StubVoiceBackendGateway()
    backend.load()
    progress = Mock()
    result = backend.run(SpeechJob("design", "Hello.", 7, {"seconds": seconds}), progress, lambda: False)
    backend.release()
    assert backend.capabilities().backend_id == "auk"
    assert result.seconds == expected
    assert result.seed == 7 and result.steps == 4
    assert [call.args for call in progress.call_args_list] == [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)]
    with wave.open(io.BytesIO(result.wav), "rb") as audio:
        assert audio.getframerate() == backend.capabilities().reference_sample_rate
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getnframes() == int(backend.capabilities().reference_sample_rate * expected)
        assert any(audio.readframes(audio.getnframes()))


def test_stub_cancels_before_any_audio_work():
    progress = Mock()
    with pytest.raises(Cancelled):
        StubVoiceBackendGateway().run(SpeechJob("design", "Hello.", 7, {}), progress, lambda: True)
    progress.assert_not_called()
