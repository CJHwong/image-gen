"""Cancel, through the server's own wiring, against an engine that says nothing.

The cancel path runs from the controller to the engine's process group, and the
piece in the middle is the progress gateway: the run asks it whether a cancel was
requested, and a cancel sets that flag. Each end is tested on its own, and this is
the two together over a child that stays quiet for a long time, which is what the
real engine does while it encodes the prompt and the images.
"""

import sys
import threading
import time
from pathlib import Path

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

FAKE = Path(__file__).with_name("fake_child.py")
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
