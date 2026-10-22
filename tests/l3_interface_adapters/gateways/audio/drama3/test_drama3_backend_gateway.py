import base64
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.voice_job import ReferenceAudio, SpeechJob
from studio.l3_interface_adapters.gateways.audio.drama3.drama3_backend_gateway import Drama3BackendGateway


def test_drama_retains_one_child_and_maps_exact_arguments():
    child = Mock()
    child.request.return_value = {
        "wav": base64.b64encode(b"wav").decode(),
        "seconds": 2.5,
        "sample_rate": 44100,
        "steps": 54,
    }
    backend = Drama3BackendGateway(child)
    assert backend.capabilities().backend_id == "drama3"
    backend.load()
    child.wait_ready.assert_called_once_with()
    progress, stop = Mock(), lambda: False
    options = {"temperature": 0.7, "max_tokens": 1024}
    result = backend.run(SpeechJob("generate", "[whispers] Hello", 7, options), progress, stop)
    assert result.wav == b"wav" and result.sample_rate == 44100 and result.seed == 7
    child.request.assert_called_with({"text": "[whispers] Hello", "seed": 7, **options}, progress, stop)
    backend.run(
        SpeechJob("clone", "New words", 8, {"ref_text": "Old words"}, (ReferenceAudio(b"ref", 1, 24000),)),
        progress,
        stop,
    )
    assert child.request.call_args.args[0] == {
        "text": "New words",
        "seed": 8,
        "ref_text": "Old words",
        "audio": base64.b64encode(b"ref").decode(),
    }
    backend.release()
    child.stop.assert_called_once_with()


def test_drama_checks_cancel_before_a_request():
    child = Mock()
    with pytest.raises(Cancelled):
        Drama3BackendGateway(child).run(SpeechJob("generate", "Hello", 7, {}), Mock(), lambda: True)
    child.request.assert_not_called()


@pytest.mark.live
def test_drama3_live_native_speech():
    from pathlib import Path

    from studio.l4_frameworks_and_drivers.config import load_config
    from studio.l4_frameworks_and_drivers.main import build_voice_backends
    from tests.support.voice_audio import read

    gateway = build_voice_backends(load_config(Path("studio.toml")))["drama3"]
    try:
        gateway.load()
        result = gateway.run(
            SpeechJob("generate", "The blue teapot is beside the window.", 7, {}), lambda *_: None, lambda: False
        )
        samples, rate = read(result.wav)
        assert rate == 44100 and len(samples) > 44100 and max(abs(samples)) > 0.01
    finally:
        gateway.release()
