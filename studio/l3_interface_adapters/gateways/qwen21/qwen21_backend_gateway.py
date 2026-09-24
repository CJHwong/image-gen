from studio.l1_entities.image_job import ImageJob
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.qwen21.capabilities import qwen21_capabilities


class Qwen21BackendGateway(ImageBackendGateway):
    """Two engines behind one backend: mflux for generate, the diffusers child for edit.

    Only one of them fits in memory. The edit engine loads the full Qwen3-VL,
    vision tower included, and measured 38.7 GiB allocated on MPS; mflux peaks
    at 30.7 GB. Both would not fit on a 64 GB machine, so each run frees the
    other engine first. Rebuilding the mflux model after an edit measured 3.8s.
    """

    def __init__(self, generator, edit, badge: str):
        self._generator = generator
        self._edit = edit
        self._badge = badge

    def capabilities(self):
        return qwen21_capabilities(self._badge)

    def load(self):
        self._generator.load()

    def run(self, job: ImageJob, on_step, should_stop):
        if job.mode == "edit":
            self._generator.release()
            return self._edit.run(job, on_step, should_stop)
        self._edit.release()
        return self._generator.run(job, on_step, should_stop)

    def release(self):
        self._generator.release()
        self._edit.release()
