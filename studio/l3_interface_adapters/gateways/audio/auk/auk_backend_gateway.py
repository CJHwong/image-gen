"""The AuK model, backed by the shared AuK engine adapter."""

from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway
from studio.l3_interface_adapters.gateways.audio.auk_runtime.auk_engine import AukEngine


class AukBackendGateway(VoiceBackendGateway):
    def __init__(self, child):
        self._engine = AukEngine(child, "base")

    def capabilities(self):
        return self._engine.capabilities()

    def load(self):
        self._engine.load()

    def release(self):
        self._engine.release()

    def prepare_batch(self, jobs, should_stop):
        self._engine.prepare_batch(jobs, should_stop)

    def run(self, job, on_step, should_stop):
        return self._engine.run(job, on_step, should_stop)
