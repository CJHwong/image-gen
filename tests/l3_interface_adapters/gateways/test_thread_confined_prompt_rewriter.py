import threading
from unittest.mock import Mock

import pytest

from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l3_interface_adapters.gateways.gpu_thread import GpuThread
from studio.l3_interface_adapters.gateways.thread_confined_prompt_rewriter import ThreadConfinedPromptRewriter


class Recording(PromptRewriterGateway):
    """A rewriter that notes the thread each call arrived on."""

    def __init__(self):
        self.threads = []

    def modes(self):
        return ("generate", "edit")

    def rewrite(self, prompt, mode, references):
        self.threads.append(threading.get_ident())
        return PromptRewrite(prompt=f"longer {prompt}")

    def release(self):
        self.threads.append(threading.get_ident())


def test_the_modes_come_back_without_the_gpu_thread():
    # The mode list is a plain tuple, not a model call, so it answers on the
    # calling thread. The page reads it on every request.
    rewriter = Mock(spec=PromptRewriterGateway)
    rewriter.modes.return_value = ("generate",)
    assert ThreadConfinedPromptRewriter(rewriter, GpuThread()).modes() == ("generate",)
    rewriter.modes.assert_called_once_with()


def test_a_rewrite_runs_on_the_gpu_thread_with_the_arguments_it_was_given():
    # MLX binds its streams to the thread that made them, so a rewrite called
    # straight from a request thread aborts the process.
    seen = []

    def rewrite(prompt, mode, references):
        seen.append(threading.get_ident())
        return PromptRewrite(prompt=f"longer {prompt}")

    rewriter = Mock()
    rewriter.rewrite.side_effect = rewrite
    answer = ThreadConfinedPromptRewriter(rewriter, GpuThread()).rewrite("a cat", "generate", ())
    assert answer.prompt == "longer a cat"
    assert rewriter.rewrite.call_args.args == ("a cat", "generate", ())
    assert seen != [threading.get_ident()]


def test_a_release_runs_on_the_gpu_thread():
    # Freeing the model is a model call too: the memory belongs to the thread
    # that allocated it.
    rewriter = Recording()
    ThreadConfinedPromptRewriter(rewriter, GpuThread()).release()
    assert len(rewriter.threads) == 1
    assert rewriter.threads[0] != threading.get_ident()


def test_a_failure_on_the_gpu_thread_reaches_the_caller():
    rewriter = Mock()
    rewriter.rewrite.side_effect = RuntimeError("no weights")
    with pytest.raises(RuntimeError, match="no weights"):
        ThreadConfinedPromptRewriter(rewriter, GpuThread()).rewrite("a cat", "generate", ())
