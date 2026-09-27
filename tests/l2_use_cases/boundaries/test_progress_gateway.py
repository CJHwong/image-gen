"""The port that carries the state of the one run in flight.

The run writes it on the GPU thread and the poll request reads it, so the port is
also the contract that keeps those two off each other's state. A cancel outlives
the run it landed in: a batch is a chain of separate runs.
"""

from typing import Any

import pytest

from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway

OPERATIONS = frozenset(
    {
        "begin",
        "set_step",
        "finish",
        "request_cancel",
        "cancel_requested",
        "consume_cancel",
        "clear_cancel",
        "snapshot",
    }
)


def test_the_port_cannot_be_instantiated():
    # The call is invalid by design, and the run time is what refuses it.
    # `Any` keeps the type checker from refusing the test itself.
    port_type: Any = ProgressGateway
    with pytest.raises(TypeError, match="abstract"):
        port_type()


def test_the_port_declares_the_operations_the_core_calls():
    assert ProgressGateway.__abstractmethods__ == OPERATIONS


def test_the_in_memory_adapter_satisfies_the_port():
    adapter = InMemoryProgressGateway()
    assert isinstance(adapter, ProgressGateway)
    assert not InMemoryProgressGateway.__abstractmethods__
    assert all(callable(getattr(adapter, operation)) for operation in OPERATIONS)
