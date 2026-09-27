"""Make another visible backend the active one, with one model in memory at a time.

One backend fits in memory: one Qwen-Image-2.1 engine alone peaks above 30 GB. So
the old backend is freed before the new one loads, and the switch takes the engine
lock, which is the lock a run holds, so no switch frees an engine under a run.
"""

import threading

import pytest

from studio.l1_entities.errors import BackendBusy, UnknownBackend
from studio.l2_use_cases.switch_backend_use_case import SwitchBackendUseCase
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from tests.support.fakes import FakeBackendGateway


class LoggedBackend(FakeBackendGateway):
    """A backend that writes load and release into the test's log, so the order
    across two backends is visible in one place."""

    def __init__(self, backend_id: str, name: str, log: list[str]):
        super().__init__(backend_id, name)
        self._log = log

    def load(self):
        self._log.append(f"load {self.caps.backend_id}")

    def release(self):
        self._log.append(f"release {self.caps.backend_id}")


class SwitchSetup:
    def __init__(self):
        self.log: list[str] = []
        self.first = LoggedBackend("first", "First", self.log)
        self.second = LoggedBackend("second", "Second", self.log)
        self.hidden = LoggedBackend("hidden", "Hidden", self.log)
        self.catalog = InMemoryBackendCatalogGateway(
            {"first": self.first, "second": self.second, "hidden": self.hidden},
            default_id="first",
            visible_ids=("first", "second"),
        )
        self.engine_lock = threading.Lock()


@pytest.fixture
def switch_setup():
    return SwitchSetup()


def test_a_switch_frees_the_old_backend_before_the_new_one_loads(switch_setup):
    SwitchBackendUseCase(switch_setup.catalog, switch_setup.engine_lock).execute("second")
    assert switch_setup.log == ["release first", "load second"]
    assert switch_setup.catalog.active_id() == "second"


def test_switching_to_the_backend_already_active_does_nothing(switch_setup):
    # A reload here would drop a warm engine for no gain.
    SwitchBackendUseCase(switch_setup.catalog, switch_setup.engine_lock).execute("first")
    assert switch_setup.log == []


def test_a_backend_the_page_cannot_offer_is_refused(switch_setup):
    with pytest.raises(UnknownBackend):
        SwitchBackendUseCase(switch_setup.catalog, switch_setup.engine_lock).execute("hidden")
    assert switch_setup.log == [] and switch_setup.catalog.active_id() == "first"


def test_an_unknown_backend_is_refused(switch_setup):
    with pytest.raises(UnknownBackend):
        SwitchBackendUseCase(switch_setup.catalog, switch_setup.engine_lock).execute("nope")
    assert switch_setup.catalog.active_id() == "first"


def test_a_switch_waits_rather_than_freeing_an_engine_under_a_run(switch_setup):
    with switch_setup.engine_lock, pytest.raises(BackendBusy):
        SwitchBackendUseCase(switch_setup.catalog, switch_setup.engine_lock).execute("second")
    assert switch_setup.log == [] and switch_setup.catalog.active_id() == "first"


def test_the_engine_lock_is_free_again_after_a_switch(switch_setup):
    # A switch that kept the lock would refuse every later run, and the page would
    # report a busy model with nothing running.
    SwitchBackendUseCase(switch_setup.catalog, switch_setup.engine_lock).execute("second")
    assert switch_setup.engine_lock.acquire(blocking=False) is True
    switch_setup.engine_lock.release()
