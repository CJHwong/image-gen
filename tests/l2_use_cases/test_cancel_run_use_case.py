"""Cancel, through the server's own wiring, against an engine that says nothing.

The cancel path runs from the controller to the engine's process group, and the
piece in the middle is the progress gateway: the run asks it whether a cancel was
requested, and a cancel sets that flag. Each end is tested on its own, and this is
the two together over a child that stays quiet for a long time, which is what the
real engine does while it encodes the prompt and the images.

The flag stops only the engine that looks at it, so the same use case starts one
watch per cancel: the watch frees the engine when the run is still in flight after
`patience` seconds, and leaves a warm engine warm when the run stops first.
"""

import sys
import threading
import time

from studio.l1_entities.capabilities import Capabilities, ModeSpec
from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l2_use_cases.cancel_run_use_case import CancelRunUseCase
from studio.l2_use_cases.run_image_use_case import RunImageRequest, RunImageUseCase
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway
from studio.l3_interface_adapters.gateways.in_memory_reference_store_gateway import InMemoryReferenceStoreGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from tests.support import FAKE_CHILD
from tests.support.fakes import FakeBackendGateway

FAKE = FAKE_CHILD
QUIET_SECONDS = 30  # the engine's first word is this far away


class ChildBackend(ImageBackendGateway):
    """A backend whose engine is the fake child, so the cancel reaches a process."""

    def __init__(self, child: StdioChild):
        self._child = child

    def capabilities(self):
        return Capabilities(
            backend_id="one",
            name="One",
            badge="test",
            max_batch=1,
            modes=(ModeSpec(id="generate", label="Draw", params=()),),
        )

    def load(self):
        pass

    def run(self, job, on_step, should_stop):
        # Step 0 arrives after the pause, so the engine is silent until then.
        self._child.request({"steps": 1, "pause": QUIET_SECONDS}, on_step, should_stop)
        return ImageResult(png=b"", width=1, height=1, seed=1, steps=1)

    def release(self):
        pass


def test_cancel_stops_a_run_whose_engine_is_silent():
    progress = InMemoryProgressGateway()
    child = StdioChild(["/bin/sh", "-c", f'"{sys.executable}" "{FAKE}"; exit $?'])
    catalog = InMemoryBackendCatalogGateway({"one": ChildBackend(child)}, "one", ("one",))
    run = RunImageUseCase(catalog, progress, InMemoryReferenceStoreGateway())
    cancel = CancelRunUseCase(progress, catalog)
    outcome: dict = {}

    def go():
        try:
            run.execute(RunImageRequest(mode="generate", prompt="a teapot", seed="", options={}))
        except BaseException as error:  # the test reports whatever came back
            outcome["error"] = error

    runner = threading.Thread(target=go)
    runner.start()
    time.sleep(0.5)  # the run has to be inside the engine before a cancel means anything
    began = time.time()
    cancel.execute()
    runner.join(timeout=5)
    try:
        assert not runner.is_alive(), "the cancel did not stop the run"
        assert isinstance(outcome.get("error"), Cancelled), outcome
        assert time.time() - began < 3, f"the cancel took {time.time() - began:.1f}s"
    finally:
        child.stop()


def _watch_threads(known: set[int | None]) -> list[threading.Thread]:
    """The threads this test started, which are still alive."""
    return [thread for thread in threading.enumerate() if thread.ident not in known and thread.is_alive()]


def _join_watch_threads(known: set[int | None], timeout: float = 5.0) -> None:
    """Wait for the watch threads this test started to end."""
    deadline = time.time() + timeout
    while time.time() < deadline and _watch_threads(known):
        time.sleep(0.005)


def test_a_second_cancel_while_a_watch_runs_starts_no_second_watch():
    # A double click sends two cancels. One watch per cancel is enough, because a
    # second watcher would free the same engine twice.
    backend = FakeBackendGateway()
    catalog = InMemoryBackendCatalogGateway({"fake": backend}, "fake", ("fake",))
    progress = InMemoryProgressGateway()
    progress.begin("1 of 2")
    inside = threading.Event()
    gate = threading.Event()
    waits: list[float] = []

    def wait(seconds: float) -> None:
        waits.append(seconds)
        inside.set()
        gate.wait(5)

    cancel = CancelRunUseCase(progress, catalog, patience=10.0, wait=wait)
    known = {thread.ident for thread in threading.enumerate()}
    cancel.execute()
    assert inside.wait(5), "the watch never entered its loop"
    cancel.execute()  # the second cancel lands while the first watch is running
    assert len(_watch_threads(known)) == 1, "the second cancel started a second watch"
    progress.finish()  # the run ended, so the watch returns without freeing the engine
    gate.set()
    assert waits == [0.25]
    assert backend.events == []


def test_a_run_that_stops_as_the_window_ends_keeps_its_engine():
    # The watch frees the engine only while the run is still in flight when the
    # window ends. A reload costs the next run 3.8s for mflux, so the net reads
    # the run again rather than firing on the clock alone.
    backend = FakeBackendGateway()
    catalog = InMemoryBackendCatalogGateway({"fake": backend}, "fake", ("fake",))
    progress = InMemoryProgressGateway()
    progress.begin("1 of 2")
    now = [0.0]

    def wait(seconds: float) -> None:
        now[0] = 100.0  # the window ends on this tick
        progress.finish()  # and the run stops in the same moment

    cancel = CancelRunUseCase(progress, catalog, patience=5.0, clock=lambda: now[0], wait=wait)
    known = {thread.ident for thread in threading.enumerate()}
    cancel.execute()
    _join_watch_threads(known)
    assert backend.events == []


class DeafBackend(FakeBackendGateway):
    """An engine that never looks at the cancel flag, so only freeing it stops it.

    That is the case the net is for: the flag is set, nothing reads it, and the run
    carries on while Cancel appears to do nothing.
    """

    def __init__(self):
        super().__init__()
        self.freed = threading.Event()

    def run(self, job, on_step, should_stop):
        self.jobs.append(job)
        for step in range(1, 41):
            if self.freed.wait(0.01):
                raise RuntimeError("the engine stopped answering")
            on_step(step, 40)
        return ImageResult(png=b"png", width=8, height=8, seed=job.seed, steps=40)

    def release(self):
        self.events.append("release")
        self.freed.set()


# Long enough that the cancel lands inside the engine, which is the ordinary case.
LONG_REQUEST = RunImageRequest(mode="generate", prompt="a red apple", seed="42", options={"steps": "40"})


def run_with_cancel(backend, patience=0.05):
    """Start a run, cancel it once it is inside the engine, and report what happened."""
    progress = InMemoryProgressGateway()
    catalog = InMemoryBackendCatalogGateway({"fake": backend}, "fake", ("fake",))
    run = RunImageUseCase(catalog, progress, InMemoryReferenceStoreGateway())
    cancel = CancelRunUseCase(progress, catalog, patience=patience, wait=lambda seconds: time.sleep(0.005))
    outcome: dict = {}

    def go():
        try:
            run.execute(LONG_REQUEST)
        except BaseException as error:  # the test reports whatever came back
            outcome["error"] = error

    thread = threading.Thread(target=go)
    thread.start()
    time.sleep(0.05)  # the run has to be inside the engine before a cancel means anything
    cancel.execute()
    thread.join(timeout=5)
    return thread, outcome, backend.events


def test_a_cancel_frees_an_engine_that_never_looks():
    backend = DeafBackend()
    thread, outcome, events = run_with_cancel(backend)
    assert not thread.is_alive(), "the cancel never freed the engine"
    assert isinstance(outcome.get("error"), Cancelled), outcome
    assert "release" in events, events


def test_a_cancel_an_engine_obeys_leaves_the_engine_warm():
    # Long enough per step that the cancel lands mid-run, which is the ordinary case.
    backend = FakeBackendGateway(stop_check=lambda step: time.sleep(0.02))
    thread, outcome, events = run_with_cancel(backend)
    assert not thread.is_alive()
    assert isinstance(outcome.get("error"), Cancelled), outcome
    # The net waits its window before acting, so waiting less than that would pass this
    # test even if it always fired.
    time.sleep(0.3)
    assert "release" not in events, f"the net fired on a cancel that worked: {events}"
