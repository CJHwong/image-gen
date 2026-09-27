"""What the page polls: the state of the one run in flight.

The poll request reads while the run writes on the GPU thread, so the read returns
a snapshot and never a live view. The cancel flag travels with it as `stopping`,
because the run may take a step or more to notice the request.
"""

from studio.l2_use_cases.read_progress_use_case import ReadProgressUseCase
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway


def test_an_idle_server_reports_no_run():
    state = ReadProgressUseCase(InMemoryProgressGateway()).execute()
    assert (state.running, state.stage, state.step, state.label) == (False, "", 0, "")


def test_a_run_in_flight_reports_its_stage_and_step():
    progress = InMemoryProgressGateway()
    progress.begin("2 of 4")
    preparing = ReadProgressUseCase(progress).execute()
    assert (preparing.running, preparing.stage, preparing.label) == (True, "preparing", "2 of 4")
    progress.set_step(3, 20)
    running = ReadProgressUseCase(progress).execute()
    assert (running.running, running.stage, running.step, running.total) == (True, "running", 3, 20)


def test_a_cancel_reads_as_stopping_while_the_run_is_still_running():
    # The page sets no state of its own. It draws the Cancel button from this
    # read, and a run that has not noticed the flag yet must still show as running.
    progress = InMemoryProgressGateway()
    progress.begin("")
    progress.request_cancel()
    state = ReadProgressUseCase(progress).execute()
    assert state.running is True and state.stopping is True
