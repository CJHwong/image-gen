"""The port that carries the state of the one rewrite in flight.

The rewriter writes it on its own thread and the poll request reads it, so the
port is also the contract that keeps those two off each other's state. It is
separate from the run's state, because the two jobs are separate.
"""

from typing import Any

import pytest

from studio.l2_use_cases.boundaries.rewrite_progress_gateway import RewriteProgressGateway
from studio.l3_interface_adapters.gateways.in_memory_rewrite_progress_gateway import InMemoryRewriteProgressGateway

OPERATIONS = frozenset(
    {
        "begin",
        "writing",
        "finish",
        "request_cancel",
        "cancel_requested",
        "clear_cancel",
        "snapshot",
    }
)


def test_the_port_cannot_be_instantiated():
    # The call is invalid by design, and the run time is what refuses it.
    # `Any` keeps the type checker from refusing the test itself.
    port_type: Any = RewriteProgressGateway
    with pytest.raises(TypeError, match="abstract"):
        port_type()


def test_the_port_declares_the_operations_the_core_calls():
    assert RewriteProgressGateway.__abstractmethods__ == OPERATIONS


def test_the_in_memory_adapter_satisfies_the_port():
    adapter = InMemoryRewriteProgressGateway()
    assert isinstance(adapter, RewriteProgressGateway)
    assert not InMemoryRewriteProgressGateway.__abstractmethods__
    assert all(callable(getattr(adapter, operation)) for operation in OPERATIONS)
