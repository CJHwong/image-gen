from dataclasses import dataclass


@dataclass(frozen=True)
class RunProgress:
    """What the run in flight is doing, as the page polls it.

    `stage` is "preparing" before the first step and "running" after it.
    `label` places the image in its batch, "2 of 4", or is empty for one image.
    """

    running: bool = False
    stage: str = ""
    step: int = 0
    total: int = 0
    label: str = ""
    stopping: bool = False
