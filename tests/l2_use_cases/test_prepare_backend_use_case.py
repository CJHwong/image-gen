"""Load the active backend before the first request, so the first run pays no load.

The server calls this once at start. Only the active backend loads: one model fills
the machine, and a backend the page cannot offer has no business holding memory.
"""

from studio.l2_use_cases.prepare_backend_use_case import PrepareBackendUseCase
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from tests.support.fakes import FakeBackendGateway


def test_the_active_backend_loads():
    active = FakeBackendGateway("active", "Active")
    catalog = InMemoryBackendCatalogGateway({"active": active}, default_id="active", visible_ids=("active",))
    PrepareBackendUseCase(catalog).execute()
    assert active.events == ["load"]


def test_a_backend_the_page_cannot_offer_stays_unloaded():
    # The registered set is larger than the visible one, and a hidden backend that
    # loaded here would hold a model the page never asked for.
    active = FakeBackendGateway("active", "Active")
    hidden = FakeBackendGateway("hidden", "Hidden")
    catalog = InMemoryBackendCatalogGateway(
        {"active": active, "hidden": hidden}, default_id="active", visible_ids=("active",)
    )
    PrepareBackendUseCase(catalog).execute()
    assert hidden.events == []


def test_the_load_follows_the_backend_the_page_switched_to():
    first = FakeBackendGateway("first", "First")
    second = FakeBackendGateway("second", "Second")
    catalog = InMemoryBackendCatalogGateway(
        {"first": first, "second": second}, default_id="first", visible_ids=("first", "second")
    )
    catalog.set_active("second")
    PrepareBackendUseCase(catalog).execute()
    assert first.events == [] and second.events == ["load"]
