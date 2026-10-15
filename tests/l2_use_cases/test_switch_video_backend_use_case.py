import threading

import pytest

from studio.l1_entities.errors import BackendBusy, UnknownBackend
from studio.l2_use_cases.switch_video_backend_use_case import SwitchVideoBackendUseCase
from studio.l3_interface_adapters.gateways.in_memory_model_residency_gateway import (
    InMemoryModelResidencyGateway,
)
from studio.l3_interface_adapters.gateways.in_memory_video_backend_catalog_gateway import (
    InMemoryVideoBackendCatalogGateway,
)
from tests.support.fakes import FakeVideoBackendGateway


@pytest.fixture
def setup():
    first = FakeVideoBackendGateway("first-video", "First video")
    second = FakeVideoBackendGateway("second-video", "Second video")
    catalog = InMemoryVideoBackendCatalogGateway(
        {"first-video": first, "second-video": second},
        default_id="first-video",
        visible_ids=("first-video", "second-video"),
    )
    residency = InMemoryModelResidencyGateway({"first-video": first, "second-video": second})
    residency.activate("first-video")
    return catalog, residency, threading.Lock(), first, second


def test_a_video_model_switch_releases_the_old_model_without_loading_the_new_one(setup):
    catalog, residency, lock, first, second = setup

    SwitchVideoBackendUseCase(catalog, lock, residency).execute("second-video")

    assert first.releases == 1
    assert second.releases == 0
    assert catalog.active_id() == "second-video"
    assert residency.active_id() == "second-video"


def test_switching_to_the_selected_video_model_does_nothing(setup):
    catalog, residency, lock, first, _ = setup

    SwitchVideoBackendUseCase(catalog, lock, residency).execute("first-video")

    assert first.releases == 0


def test_a_hidden_video_model_cannot_be_selected(setup):
    catalog, residency, lock, first, second = setup
    catalog = InMemoryVideoBackendCatalogGateway(
        {"first-video": first, "second-video": second},
        default_id="first-video",
        visible_ids=("first-video",),
    )

    with pytest.raises(UnknownBackend):
        SwitchVideoBackendUseCase(catalog, lock, residency).execute("second-video")

    assert catalog.active_id() == "first-video"


def test_a_busy_model_cannot_be_switched(setup):
    catalog, residency, lock, first, _ = setup
    lock.acquire()

    with pytest.raises(BackendBusy):
        SwitchVideoBackendUseCase(catalog, lock, residency).execute("second-video")

    assert first.releases == 0
    assert catalog.active_id() == "first-video"
    lock.release()
