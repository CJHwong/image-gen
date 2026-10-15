import pytest

from studio.l1_entities.errors import UnknownBackend
from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway
from studio.l3_interface_adapters.gateways.in_memory_model_residency_gateway import (
    InMemoryModelResidencyGateway,
)


class Runtime(ModelLifecycleGateway):
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def release(self) -> None:
        self.events.append("release " + self.name)


def test_claiming_a_different_model_releases_the_previous_model_without_loading_the_new_one():
    events = []
    residency = InMemoryModelResidencyGateway({"image": Runtime("image", events), "video": Runtime("video", events)})

    residency.activate("image")
    residency.activate("video")

    assert events == ["release image"]
    assert residency.active_id() == "video"


def test_claiming_the_same_model_keeps_it_resident():
    events = []
    residency = InMemoryModelResidencyGateway({"image": Runtime("image", events)})
    residency.activate("image")

    residency.activate("image")

    assert events == []


def test_releasing_an_idle_model_is_safe():
    events = []
    residency = InMemoryModelResidencyGateway({"image": Runtime("image", events)})

    residency.release()
    residency.activate("image")
    residency.release()
    residency.release()

    assert events == ["release image"]
    assert residency.active_id() is None


def test_a_model_outside_the_registry_is_refused():
    residency = InMemoryModelResidencyGateway({})

    with pytest.raises(UnknownBackend, match="no runtime registered as missing"):
        residency.activate("missing")
