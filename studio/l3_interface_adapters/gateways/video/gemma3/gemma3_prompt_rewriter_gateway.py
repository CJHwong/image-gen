"""LTX's native Gemma 3 prompt enhancer, shared by its video models."""

from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway


class Gemma3PromptRewriterGateway(PromptRewriterGateway):
    def __init__(self, enhancer):
        self._enhancer = enhancer

    def modes(self):
        return ("generate",)

    def rewrite(self, prompt, mode, references, on_writing, should_stop):
        return PromptRewrite(self._enhancer(prompt, references, on_writing, should_stop))

    def release(self):
        # Each enhancement child frees its model before returning.
        pass
