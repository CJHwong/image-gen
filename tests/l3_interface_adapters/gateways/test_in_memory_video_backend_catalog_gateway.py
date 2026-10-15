import pytest

from studio.l1_entities.errors import UnknownBackend
from studio.l3_interface_adapters.gateways.in_memory_video_backend_catalog_gateway import (
    InMemoryVideoBackendCatalogGateway,
)
from tests.support.fakes import FakeVideoBackendGateway


def test_video_models_keep_their_registration_and_display_order():
    first = FakeVideoBackendGateway("first", "First")
    second = FakeVideoBackendGateway("second", "Second")
    catalog = InMemoryVideoBackendCatalogGateway({"first": first, "second": second}, "first", ("second", "first"))

    assert catalog.get("second") is second
    assert catalog.visible_ids() == ("second", "first")
    assert catalog.active_id() == "first"


def test_only_registered_video_models_can_be_selected():
    first = FakeVideoBackendGateway("first", "First")
    catalog = InMemoryVideoBackendCatalogGateway({"first": first}, "first", ("first",))

    with pytest.raises(UnknownBackend, match="no video backend registered as missing"):
        catalog.set_active("missing")

    assert catalog.active_id() == "first"


def test_a_catalog_refuses_unregistered_defaults_and_visible_models():
    first = FakeVideoBackendGateway("first", "First")

    with pytest.raises(UnknownBackend, match="no video backend registered as missing"):
        InMemoryVideoBackendCatalogGateway({"first": first}, "missing", ("first",))
