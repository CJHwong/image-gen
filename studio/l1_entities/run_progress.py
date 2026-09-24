from dataclasses import dataclass


@dataclass(frozen=True)
class RunProgress:
    """What the run in flight is doing, as the page polls it.

    `stage` is "preparing" while the backend sets up its model, and "running"
    from its step 0 notice on.
    `label` places the image in its batch, "2 of 4", or is empty for one image.
    """

    running: bool = False
    stage: str = ""
    step: int = 0
    total: int = 0
    label: str = ""
    stopping: bool = False
