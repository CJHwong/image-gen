"""Ordered speech jobs share the resident engine and its encoded-reference cache."""

import base64

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.voice_job import SpeechResult
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway
from studio.l3_interface_adapters.gateways.drama_voice.capabilities import drama_capabilities


class DramaBackendGateway(VoiceBackendGateway):
    def __init__(self, child):
        self._child = child

    def capabilities(self):
        return drama_capabilities()

    def load(self):
        self._child.wait_ready()

    def release(self):
        self._child.stop()

    def run(self, job, on_step, should_stop):
        if should_stop():
            raise Cancelled("Voice generation was cancelled.")
        payload = {"text": job.text, "seed": job.seed, **job.options}
        if job.references:
            payload["audio"] = base64.b64encode(job.references[0].wav).decode("ascii")
        reply = self._child.request(payload, on_step, should_stop)
        return SpeechResult(
            base64.b64decode(reply["wav"]), reply["seconds"], reply["sample_rate"], job.seed, reply["steps"]
        )
