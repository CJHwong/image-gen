"""A short playable WAV for Voice interface checks without a model."""

import io
import math
import struct
import time
import wave

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.voice_job import SpeechResult
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway
from studio.l3_interface_adapters.gateways.auk_voice.capabilities import auk_capabilities


class StubVoiceBackendGateway(VoiceBackendGateway):
    def __init__(self, variant="flash", capabilities=None):
        self._capabilities = capabilities or auk_capabilities(variant)

    def capabilities(self):
        return self._capabilities

    def load(self):
        pass

    def release(self):
        pass

    def run(self, job, on_step, should_stop):
        for step in range(4):
            if should_stop():
                raise Cancelled("Voice generation was cancelled.")
            on_step(step, 4)
            time.sleep(0.08)
        rate = self._capabilities.reference_sample_rate
        seconds = float(job.options.get("seconds", 0)) or 1.0
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(
                b"".join(
                    struct.pack("<h", int(800 * math.sin(index * 2 * math.pi * 220 / rate)))
                    for index in range(int(rate * seconds))
                )
            )
        on_step(4, 4)
        return SpeechResult(buffer.getvalue(), seconds, rate, job.seed, 4)
