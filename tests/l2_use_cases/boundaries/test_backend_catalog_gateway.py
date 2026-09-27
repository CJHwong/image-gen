"""The port the core resolves every backend through, and the in-memory adapter.

A port that can be built with no behaviour, or an adapter that skips one
operation, has to fail at construction. The failure at build time is what keeps
an unimplemented `get` out of the first request the page makes.
"""

from typing import Any

import pytest

from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from tests.support.fakes import FakeBackendGateway

OPERATIONS = frozenset({"get", "visible_ids", "active_id", "set_active"})


def test_the_port_cannot_be_instantiated():
    # The call is invalid by design, and the run time is what refuses it.
    # `Any` keeps the type checker from refusing the test itself.
    port_type: Any = BackendCatalogGateway
    with pytest.raises(TypeError, match="abstract"):
        port_type()


def test_the_port_declares_the_operations_the_core_calls():
    assert BackendCatalogGateway.__abstractmethods__ == OPERATIONS


def test_the_in_memory_adapter_satisfies_the_port():
    adapter = InMemoryBackendCatalogGateway({"fake": FakeBackendGateway()}, default_id="fake", visible_ids=("fake",))
    assert isinstance(adapter, BackendCatalogGateway)
    assert not InMemoryBackendCatalogGateway.__abstractmethods__
    assert all(callable(getattr(adapter, operation)) for operation in OPERATIONS)
