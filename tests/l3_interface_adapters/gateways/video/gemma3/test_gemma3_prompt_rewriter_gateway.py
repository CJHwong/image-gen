from studio.l3_interface_adapters.gateways.video.gemma3.gemma3_prompt_rewriter_gateway import (
    Gemma3PromptRewriterGateway,
)


def test_native_video_enhancement_passes_conditioning_and_callbacks():
    calls = []
    writing, stop = object(), object()
    gateway = Gemma3PromptRewriterGateway(lambda *args: calls.append(args) or "A directed shot.")
    assert gateway.modes() == ("generate",)
    assert gateway.rewrite("A cat", "generate", (), writing, stop).prompt == "A directed shot."
    references = (object(),)
    gateway.rewrite("A cat", "generate", references, writing, stop)
    assert calls == [("A cat", (), writing, stop), ("A cat", references, writing, stop)]
    gateway.release()
