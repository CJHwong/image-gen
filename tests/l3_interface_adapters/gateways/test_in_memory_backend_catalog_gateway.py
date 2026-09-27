import pytest

from studio.l1_entities.errors import UnknownBackend
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from tests.support.fakes import FakeBackendGateway


def build(default_id="first", visible_ids=("first", "second")):
    """The three registered backends, one of them hidden from the page."""
    backends = {
        "first": FakeBackendGateway("first", "First"),
        "second": FakeBackendGateway("second", "Second"),
        "hidden": FakeBackendGateway("hidden", "Hidden"),
    }
    return InMemoryBackendCatalogGateway(backends, default_id=default_id, visible_ids=visible_ids), backends


def test_a_registered_backend_comes_back_under_its_id():
    catalog, backends = build()
    assert catalog.get("second") is backends["second"]


def test_an_id_nobody_registered_is_refused():
    # An id that names no backend is a wiring mistake or a stale page. Answering
    # None would turn it into an attribute error three calls later.
    catalog, _ = build()
    with pytest.raises(UnknownBackend, match="no backend registered as nope"):
        catalog.get("nope")


def test_the_page_may_offer_a_backend_that_is_not_the_default():
    # Registration and visibility are two questions. A backend can be resident
    # and answerable while the page offers no chip for it.
    catalog, backends = build()
    assert catalog.visible_ids() == ("first", "second")
    assert catalog.get("hidden") is backends["hidden"]
    assert "hidden" not in catalog.visible_ids()


def test_the_page_offers_the_visible_backends_in_the_order_it_was_given():
    # The page draws its chips in this order, so the order is part of the answer.
    catalog, _ = build(visible_ids=("second", "first"))
    assert catalog.visible_ids() == ("second", "first")


def test_the_page_starts_on_the_default_backend():
    catalog, _ = build()
    assert catalog.active_id() == "first"


def test_the_default_backend_need_not_be_one_the_page_offers():
    # A hidden default is a real configuration: the page draws no chip for it and
    # still reads its form.
    catalog, _ = build(default_id="hidden", visible_ids=("first",))
    assert catalog.active_id() == "hidden"
    assert catalog.visible_ids() == ("first",)


def test_setting_the_active_backend_moves_the_page():
    catalog, _ = build()
    catalog.set_active("second")
    assert catalog.active_id() == "second"


def test_an_id_nobody_registered_does_not_become_the_active_backend():
    # The switch has to fail before it moves anything, or the page reads a form
    # for a backend that cannot answer.
    catalog, _ = build()
    with pytest.raises(UnknownBackend, match="no backend registered as nope"):
        catalog.set_active("nope")
    assert catalog.active_id() == "first"


def test_a_catalog_built_on_an_unregistered_id_is_refused():
    # The server registers the backends it was built with. An id that names none
    # of them must fail at build time, not on the first request from the page.
    first = FakeBackendGateway("first", "First")
    with pytest.raises(UnknownBackend, match="nowhere, hidden"):
        InMemoryBackendCatalogGateway({"first": first}, default_id="nowhere", visible_ids=("hidden",))


def test_the_catalog_keeps_its_own_copy_of_the_registry():
    # A caller that keeps building backends into the dict it passed must not
    # change what the server offers after start.
    catalog, backends = build()
    backends["third"] = FakeBackendGateway("third", "Third")
    with pytest.raises(UnknownBackend):
        catalog.get("third")
