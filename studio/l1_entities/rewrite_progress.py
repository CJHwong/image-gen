from dataclasses import dataclass


@dataclass(frozen=True)
class RewriteProgress:
    """What the rewrite in flight is doing, as the page polls it.

    `stage` is "preparing" from the moment a rewrite is asked for, which is when
    the rewriter's weights load if they are cold, and "writing" from the first
    segment the model writes. "idle" means no rewrite is in flight.
    The rewriter reports no step count, so this carries none.
    """

    running: bool = False
    stage: str = "idle"
    stopping: bool = False
