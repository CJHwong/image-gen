"""Cancel, through the server's own wiring, against the rewrite in flight.

The piece in the middle is the rewrite progress gateway: the rewriter asks it
whether a cancel was requested, and a cancel sets that flag. Each end is tested on
its own, and this is the two together.

There is nothing to escalate here. The rewriter checks the flag before its first
segment and between segments, so a stop is always observed, and the use case that
owns the rewrite frees the rewriter after its own loop has stopped.
"""

from studio.l2_use_cases.cancel_rewrite_use_case import CancelRewriteUseCase
from studio.l3_interface_adapters.gateways.in_memory_rewrite_progress_gateway import InMemoryRewriteProgressGateway


def test_a_cancel_sets_the_flag_the_rewriter_reads():
    progress = InMemoryRewriteProgressGateway()
    progress.begin()
    CancelRewriteUseCase(progress).execute()
    assert progress.cancel_requested() is True
    assert progress.snapshot().stopping is True
