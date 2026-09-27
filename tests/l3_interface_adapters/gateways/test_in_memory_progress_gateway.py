import pytest

from studio.l1_entities.run_progress import RunProgress
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway


@pytest.fixture
def progress():
    return InMemoryProgressGateway()


def test_the_page_sees_the_run_start_before_its_first_step(progress):
    # The backend builds its model first, so stage is "preparing" until a step
    # notice arrives. Without that the page shows a run that never started.
    progress.begin("2 of 4")
    state = progress.snapshot()
    assert (state.running, state.stage, state.label, state.step, state.total) == (True, "preparing", "2 of 4", 0, 0)


def test_a_step_keeps_the_label_of_the_image_it_belongs_to(progress):
    progress.begin("2 of 4")
    progress.set_step(7, 25)
    state = progress.snapshot()
    assert (state.running, state.stage, state.step, state.total, state.label) == (True, "running", 7, 25, "2 of 4")


def test_finish_puts_the_state_back_to_idle(progress):
    progress.begin("")
    progress.set_step(3, 25)
    progress.finish()
    assert progress.snapshot() == RunProgress()


def test_a_fresh_gateway_says_nothing_is_running(progress):
    assert progress.snapshot() == RunProgress()


def test_the_snapshot_says_a_cancel_is_pending(progress):
    # The page polls, and the flag is what turns its button into "stopping".
    progress.request_cancel()
    assert progress.snapshot().stopping is True


def test_a_cancel_outlives_the_run_it_landed_in(progress):
    # A batch is a chain of separate runs, so a cancel between two of them must
    # still stop the batch. Consuming it is what ends it.
    progress.begin("")
    progress.request_cancel()
    assert progress.cancel_requested() is True
    assert progress.consume_cancel() is True
    assert progress.consume_cancel() is False


def test_a_fresh_batch_clears_a_stale_cancel(progress):
    progress.request_cancel()
    progress.clear_cancel()
    assert progress.cancel_requested() is False
