import pytest

from studio.l1_entities.rewrite_progress import RewriteProgress
from studio.l3_interface_adapters.gateways.in_memory_rewrite_progress_gateway import InMemoryRewriteProgressGateway


@pytest.fixture
def progress():
    return InMemoryRewriteProgressGateway()


def test_the_page_sees_the_rewrite_start_before_its_first_segment(progress):
    # The rewriter loads its weights first, so stage is "preparing" until a
    # segment arrives. Without that the page shows a rewrite that never started.
    progress.begin()
    state = progress.snapshot()
    assert (state.running, state.stage) == (True, "preparing")


def test_the_first_segment_moves_the_stage_to_writing(progress):
    progress.begin()
    progress.writing()
    state = progress.snapshot()
    assert (state.running, state.stage) == (True, "writing")


def test_finish_puts_the_state_back_to_idle(progress):
    progress.begin()
    progress.writing()
    progress.finish()
    assert progress.snapshot() == RewriteProgress()


def test_a_fresh_gateway_says_nothing_is_running(progress):
    assert progress.snapshot() == RewriteProgress()


def test_a_fresh_gateway_has_no_cancel_pending(progress):
    assert progress.cancel_requested() is False


def test_the_snapshot_says_a_cancel_is_pending(progress):
    # The page polls, and the flag is what turns its button into "stopping".
    progress.request_cancel()
    assert progress.snapshot().stopping is True


def test_the_cancel_flag_is_what_a_cancel_asked_for(progress):
    progress.request_cancel()
    assert progress.cancel_requested() is True


def test_a_cancel_asked_for_before_a_rewrite_starts_does_not_stop_that_rewrite(progress):
    # The page can send a cancel while no rewrite is in flight. A rewrite that
    # starts after it must not be born cancelled, so the owner clears the flag
    # before begin(). The gateway does not clear it in begin() or in finish():
    # begin() does not own that call, and finish() leaves the flag so the page
    # can still read `stopping` while the stop is being applied.
    progress.request_cancel()
    progress.clear_cancel()
    progress.begin()
    assert progress.cancel_requested() is False
    assert progress.snapshot().stopping is False
