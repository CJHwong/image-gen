"""The port that holds the reference images for the life of one batch.

The page sends the pictures once and every later image of the batch carries only
the token, so `get` has to answer None for a token the store dropped rather than
raise, and `drop` has to survive a token that was already dropped.
"""

from typing import Any

import pytest

from studio.l2_use_cases.boundaries.reference_store_gateway import ReferenceStoreGateway
from studio.l3_interface_adapters.gateways.in_memory_reference_store_gateway import InMemoryReferenceStoreGateway

OPERATIONS = frozenset({"add", "get", "drop"})


def test_the_port_cannot_be_instantiated():
    # The call is invalid by design, and the run time is what refuses it.
    # `Any` keeps the type checker from refusing the test itself.
    port_type: Any = ReferenceStoreGateway
    with pytest.raises(TypeError, match="abstract"):
        port_type()


def test_the_port_declares_the_operations_the_core_calls():
    assert ReferenceStoreGateway.__abstractmethods__ == OPERATIONS


def test_the_in_memory_adapter_satisfies_the_port():
    adapter = InMemoryReferenceStoreGateway()
    assert isinstance(adapter, ReferenceStoreGateway)
    assert not InMemoryReferenceStoreGateway.__abstractmethods__
    assert all(callable(getattr(adapter, operation)) for operation in OPERATIONS)
