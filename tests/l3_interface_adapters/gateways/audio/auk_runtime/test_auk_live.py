"""Run with STUDIO_LIVE_AUK=1 after the shared GPU slot is free."""

import io
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.voice_job import ReferenceAudio, SpeechJob
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.main import VOICE_BACKENDS


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("STUDIO_LIVE_AUK") != "1", reason="requires an exclusive AuK GPU slot")
@pytest.mark.parametrize("variant", ["flash", "base"])
def test_auk_live_design_clone_edit_and_cancel(tmp_path, variant):
    backend = VOICE_BACKENDS["auk" if variant == "flash" else "auk_base"](load_config(Path("studio.toml")))
    options = {
        "seconds": 4,
        "convert": "off",
        "voice": "A woman in her thirties, calm, warm and clear, reading a documentary at a steady pace with a neutral American accent.",
    }

    def generate(job):
        steps = []
        result = backend.run(job, lambda step, total: steps.append((step, total)), lambda: False)
        assert steps and all(0 <= step <= total for step, total in steps)
        assert any(step > 0 for step, _total in steps)
        assert any(step == total and total > 0 for step, total in steps)
        return result

    try:
        backend.load()
        designed = generate(SpeechJob("design", "The morning sun shines on the river and the birds sing.", 7, options))
        reference = ReferenceAudio(designed.wav, designed.seconds, designed.sample_rate)
        cloned = generate(SpeechJob("clone", "Please bring my blue bag to the front desk.", 8, options, (reference,)))
        edited = generate(SpeechJob("edit", "Increase the volume by 5 dB.", 9, options, (reference,)))
        for name, result in (("design", designed), ("clone", cloned), ("edit", edited)):
            samples, rate = soundfile.read(io.BytesIO(result.wav))
            assert result.seconds == pytest.approx(4, abs=0.1)
            assert rate == result.sample_rate and np.isfinite(samples).all()
            assert np.max(np.abs(samples)) > 0.001
            (tmp_path / (name + ".wav")).write_bytes(result.wav)
        with pytest.raises(Cancelled):
            backend.run(
                SpeechJob("clone", "This take stops before completion.", 10, options, (reference,)),
                lambda *_: None,
                lambda: True,
            )
    finally:
        backend.release()
