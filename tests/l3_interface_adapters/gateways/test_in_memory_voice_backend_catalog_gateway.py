import threading
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import BackendBusy, UnknownBackend
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway
from studio.l2_use_cases.switch_voice_backend_use_case import SwitchVoiceBackendUseCase
from studio.l3_interface_adapters.gateways.in_memory_model_residency_gateway import InMemoryModelResidencyGateway
from studio.l3_interface_adapters.gateways.in_memory_voice_backend_catalog_gateway import (
    InMemoryVoiceBackendCatalogGateway,
)


def catalog_setup(visible=("auk", "auk_base")):
    first, second = Mock(spec=VoiceBackendGateway), Mock(spec=VoiceBackendGateway)
    catalog = InMemoryVoiceBackendCatalogGateway({"auk": first, "auk_base": second}, "auk", visible)
    residency = InMemoryModelResidencyGateway({"auk": first, "auk_base": second})
    residency.activate("auk")
    return catalog, residency, threading.Lock(), first, second


def test_voice_catalog_order_lookup_and_switch_release():
    catalog, residency, lock, first, second = catalog_setup(("auk_base", "auk"))
    assert catalog.visible_ids() == ("auk_base", "auk")
    assert catalog.get("auk_base") is second
    assert catalog.active_id() == "auk"
    SwitchVoiceBackendUseCase(catalog, lock, residency).execute("auk_base")
    assert catalog.active_id() == "auk_base"
    assert residency.active_id() == "auk_base"
    first.release.assert_called_once()
    second.load.assert_not_called()


def test_voice_switch_same_hidden_unknown_and_busy_models():
    catalog, residency, lock, first, _ = catalog_setup()
    switch = SwitchVoiceBackendUseCase(catalog, lock, residency)
    switch.execute("auk")
    first.release.assert_not_called()
    with pytest.raises(UnknownBackend):
        catalog.get("missing")
    with pytest.raises(UnknownBackend):
        InMemoryVoiceBackendCatalogGateway({}, "auk", ("auk",))
    with pytest.raises(UnknownBackend):
        SwitchVoiceBackendUseCase(catalog_setup(("auk",))[0], lock, residency).execute("auk_base")
    with lock, pytest.raises(BackendBusy):
        switch.execute("auk_base")
    assert catalog.active_id() == "auk"
