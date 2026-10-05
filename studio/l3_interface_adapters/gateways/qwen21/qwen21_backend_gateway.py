from studio.l1_entities.image_job import ImageJob
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.qwen21.capabilities import qwen21_capabilities


class Qwen21BackendGateway(ImageBackendGateway):
    """Two mflux models behind one backend: the text-to-image variant for generate,
    the instruction-edit variant for edit.

    The edit variant builds the Qwen3-VL vision tower that the text-to-image
    variant never loads, so the two do not both fit on a 64 GB machine and each
    run frees the other model first. The generate peak measured 30.68 GB.
    Rebuilding the generate model after an edit measured 3.8s.
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
