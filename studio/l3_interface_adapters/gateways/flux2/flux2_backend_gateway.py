from studio.l1_entities.image_job import ImageJob
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.flux2.capabilities import flux2_capabilities


class Flux2BackendGateway(ImageBackendGateway):
    """FLUX.2 klein-base-9B. One mflux model at a time, for the mode in use."""

    def __init__(self, models, badge: str):
        self._models = models
        self._badge = badge

    def capabilities(self):
        return flux2_capabilities(self._badge)

    def load(self):
        self._models.load()

    def run(self, job: ImageJob, on_step, should_stop):
        return self._models.run(job, on_step, should_stop)

    def release(self):
        self._models.release()
