"""The port one prompt rewriter answers, and not part of any image backend.

A rewriter is a second model and cannot be resident beside an image engine, so
`release` belongs to the port. The mode list is the page's toggle: an empty tuple
hides it, and a rewriter that names no mode is never asked to rewrite.
"""

from typing import Any

import pytest

from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l3_interface_adapters.gateways.prompt_rewriters import (
    CatalogPromptRewriter,
    NoPromptRewriter,
    StubPromptRewriter,
)
from studio.l3_interface_adapters.gateways.thread_confined_prompt_rewriter import ThreadConfinedPromptRewriter

OPERATIONS = frozenset({"modes", "rewrite", "release"})
CLASS_ONLY_ADAPTERS = (CatalogPromptRewriter, ThreadConfinedPromptRewriter)


def test_the_port_cannot_be_instantiated():
    # The call is invalid by design, and the run time is what refuses it.
    # `Any` keeps the type checker from refusing the test itself.
    port_type: Any = PromptRewriterGateway
    with pytest.raises(TypeError, match="abstract"):
        port_type()


def test_the_port_declares_the_operations_the_core_calls():
    assert PromptRewriterGateway.__abstractmethods__ == OPERATIONS


@pytest.mark.parametrize("adapter", [NoPromptRewriter, StubPromptRewriter])
def test_a_rewriter_with_no_model_satisfies_the_port(adapter):
    built = adapter()
    assert isinstance(built, PromptRewriterGateway)
    assert not built.__abstractmethods__
    assert all(callable(getattr(built, operation)) for operation in OPERATIONS)


@pytest.mark.parametrize("adapter", CLASS_ONLY_ADAPTERS)
def test_every_rewriter_adapter_satisfies_the_port(adapter):
    # Class level: the catalog rewriter needs a catalog, and the thread-confined
    # one starts its GPU thread on construction.
    assert issubclass(adapter, PromptRewriterGateway)
    assert not adapter.__abstractmethods__
    assert all(callable(getattr(adapter, operation)) for operation in OPERATIONS)
