import threading

import pytest

from studio.l1_entities.errors import BackendBusy, UnknownBackend
from studio.l2_use_cases.describe_studio_use_case import DescribeStudioUseCase
from studio.l2_use_cases.switch_backend_use_case import SwitchBackendUseCase
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from tests.unit.fakes import FakeBackendGateway


@pytest.fixture
def parts():
    first, second, hidden = (
        FakeBackendGateway("first", "First"),
        FakeBackendGateway("second", "Second"),
        FakeBackendGateway("hidden"),
    )
    catalog = InMemoryBackendCatalogGateway(
        {"first": first, "second": second, "hidden": hidden}, default_id="first", visible_ids=("first", "second")
    )
    return catalog, threading.Lock(), first, second


def test_the_page_sees_the_active_backend_and_the_visible_ones(parts):
    catalog, _, _, _ = parts
    view = DescribeStudioUseCase(catalog).execute()
    assert view.active.backend_id == "first"
    assert view.backends == (("first", "First"), ("second", "Second"))


def test_a_switch_frees_the_old_backend_before_the_new_one_loads(parts):
    catalog, engine_lock, first, second = parts
    SwitchBackendUseCase(catalog, engine_lock).execute("second")
    assert catalog.active_id() == "second"
    assert first.events == ["release"] and second.events == ["load"]


def test_switching_to_the_active_backend_does_nothing(parts):
    catalog, engine_lock, first, _ = parts
    SwitchBackendUseCase(catalog, engine_lock).execute("first")
    assert first.events == []


def test_no_switch_while_the_engine_is_in_use(parts):
    catalog, engine_lock, first, _ = parts
    with engine_lock, pytest.raises(BackendBusy):
        SwitchBackendUseCase(catalog, engine_lock).execute("second")
    assert catalog.active_id() == "first" and first.events == []


@pytest.mark.parametrize("backend_id", ["nope", "hidden"])
def test_only_a_visible_backend_can_be_picked(parts, backend_id):
    catalog, engine_lock, _, _ = parts
    with pytest.raises(UnknownBackend):
        SwitchBackendUseCase(catalog, engine_lock).execute(backend_id)
