from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l3_interface_adapters.gateways.gpu_thread import GpuThread


class ThreadConfinedPromptRewriter(PromptRewriterGateway):
    """A rewriter whose rewrite and release both happen on the GPU thread.

    MLX binds its streams to the thread that made them, and the HTTP server
    answers each request on a fresh thread, so a rewriter called straight from a
    request thread would abort the process.
    """

    def __init__(self, rewriter: PromptRewriterGateway, thread: GpuThread):
        self._rewriter = rewriter
        self._thread = thread

    def modes(self):
        return self._rewriter.modes()

    def rewrite(self, prompt, mode, references, on_writing, should_stop):
        return self._thread.call(self._rewriter.rewrite, prompt, mode, references, on_writing, should_stop)

    def release(self):
        self._thread.call(self._rewriter.release)
