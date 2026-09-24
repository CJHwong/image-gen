from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.gpu_thread import GpuThread


class ThreadConfinedBackendGateway(ImageBackendGateway):
    """A backend whose load, run and release all happen on the GPU thread."""

    def __init__(self, backend: ImageBackendGateway, thread: GpuThread):
        self._backend = backend
        self._thread = thread

    def capabilities(self):
        return self._backend.capabilities()

    def load(self):
        self._thread.call(self._backend.load)

    def run(self, job, on_step, should_stop):
        return self._thread.call(self._backend.run, job, on_step, should_stop)

    def release(self):
        self._thread.call(self._backend.release)
