"""The port one model backend answers: what it can do, and how it runs one image.

Every adapter in `studio/l3_interface_adapters/gateways/` implements this port, and
the core holds no other handle on an engine. An adapter that skips `release` would
hold a model in memory for the life of the process, so the port has to refuse it.
"""

from typing import Any

import pytest

from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.stub_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.thread_confined_backend_gateway import ThreadConfinedBackendGateway

OPERATIONS = frozenset({"capabilities", "load", "run", "release"})
ADAPTERS = (ThreadConfinedBackendGateway, StubBackendGateway)


def test_the_port_cannot_be_instantiated():
    # The call is invalid by design, and the run time is what refuses it.
    # `Any` keeps the type checker from refusing the test itself.
    port_type: Any = ImageBackendGateway
    with pytest.raises(TypeError, match="abstract"):
        port_type()


def test_the_port_declares_the_operations_the_core_calls():
    assert ImageBackendGateway.__abstractmethods__ == OPERATIONS


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_every_adapter_satisfies_the_port(adapter):
    # Class level, because a thread-confined adapter starts its GPU thread on
    # construction and a test holds no GPU.
    assert issubclass(adapter, ImageBackendGateway)
    assert not adapter.__abstractmethods__
    assert all(callable(getattr(adapter, operation)) for operation in OPERATIONS)
