"""A small WAV tone demonstrates the Voice contract; it is not speech synthesis."""

import io
import math
import struct
import wave

from studio.plugins import ModelPlugin
from studio.plugins.audio import Cancelled, Capabilities, ModeSpec, ParamSpec, SpeechResult, VoiceBackendGateway

CAPABILITIES = Capabilities(
    backend_id="example_voice",
    name="Example Voice",
    badge="CPU",
    max_batch=16,
    modes=(
        ModeSpec(
            "generate",
            "Generate",
            (ParamSpec("seed", "number", 7, minimum=0, maximum=2147483647, integer=True),),
            text_hint="Write anything to create a demo tone; this plugin does not synthesize speech.",
        ),
    ),
    default_mode="generate",
)


class ExampleVoiceGateway(VoiceBackendGateway):
    def capabilities(self):
        return CAPABILITIES

    def load(self):
        pass

    def run(self, job, on_step, should_stop):
        if should_stop():
            raise Cancelled("Example Voice stopped")
        rate = 24000
        frequency = 220 + job.seed % 400
        output = io.BytesIO()
        with wave.open(output, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            stream.writeframes(
                b"".join(
                    struct.pack("<h", int(2000 * math.sin(index * 2 * math.pi * frequency / rate)))
                    for index in range(rate)
                )
            )
        on_step(1, 1)
        return SpeechResult(output.getvalue(), 1, rate, job.seed, 1, job.text)

    def release(self):
        pass


plugin = ModelPlugin(CAPABILITIES, lambda context: ExampleVoiceGateway())
