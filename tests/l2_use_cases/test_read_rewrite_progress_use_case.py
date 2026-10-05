"""What the page polls: the state of the one rewrite in flight.

The poll request reads while the rewriter writes on its own thread, so the read
returns a snapshot and never a live view. The cancel flag travels with it as
`stopping`, because the rewriter may take a segment to notice the request.
"""

from studio.l2_use_cases.read_rewrite_progress_use_case import ReadRewriteProgressUseCase
from studio.l3_interface_adapters.gateways.in_memory_rewrite_progress_gateway import InMemoryRewriteProgressGateway


def test_an_idle_server_reports_no_rewrite():
    state = ReadRewriteProgressUseCase(InMemoryRewriteProgressGateway()).execute()
    assert (state.running, state.stage) == (False, "idle")


def test_a_rewrite_in_flight_reports_its_stage():
    progress = InMemoryRewriteProgressGateway()
    progress.begin()
    preparing = ReadRewriteProgressUseCase(progress).execute()
    assert (preparing.running, preparing.stage) == (True, "preparing")
    progress.writing()
    writing = ReadRewriteProgressUseCase(progress).execute()
    assert (writing.running, writing.stage) == (True, "writing")


def test_a_cancel_reads_as_stopping_while_the_rewrite_is_still_running():
    # The page sets no state of its own. It draws the Cancel button from this
    # read, and a rewrite that has not noticed the flag yet must still show as
    # running.
    progress = InMemoryRewriteProgressGateway()
    progress.begin()
    progress.request_cancel()
    state = ReadRewriteProgressUseCase(progress).execute()
    assert state.running is True and state.stopping is True
