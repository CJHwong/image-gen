"""A backend with a real form and no engine, for work on the page.

It takes a real backend's capabilities, so the page shows that backend's
controls, and fakes only the run: timed steps and a placeholder image. It
loads no weights and never touches the GPU, so the page can be tested while
a real server holds the model.
"""

import colorsys
import random
import time

from PIL import Image, ImageDraw

from studio.l1_entities.capabilities import Capabilities
from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.image_sizes import match_reference_size
from studio.l3_interface_adapters.gateways.png_images import to_png

MATCH = "match"  # the size value every backend uses for "keep the reference's size"


def image_size(job: ImageJob) -> tuple[int, int]:
    size = str(job.options.get("size", MATCH))
    if size != MATCH:
        width, height = (int(side) for side in size.split("x"))
        return width, height
    resolution = str(job.options.get("resolution", MATCH))
    if resolution != MATCH:
        return int(resolution), int(resolution)
    if job.references:
        return match_reference_size(job.references[-1].width, job.references[-1].height)
    return 1024, 1024


def steps_to_run(job: ImageJob) -> int:
    """mflux skips the start of the schedule for a starting image. The stub
    does the same, so the page sees the same step counts as on the engine."""
    steps = int(job.options["steps"])
    if job.mode == "generate" and job.references and "strength" in job.options:
        return steps - max(1, int(steps * float(job.options["strength"])))
    return steps


def placeholder(job: ImageJob, width: int, height: int) -> Image.Image:
    """A soft gradient in a hue the seed picks, with the prompt on it."""
    hue = random.Random(job.seed).random()
    top = tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, 0.35, 0.55))
    bottom = tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, 0.5, 0.2))
    image = Image.linear_gradient("L").resize((width, height))
    image = Image.composite(Image.new("RGB", (width, height), bottom), Image.new("RGB", (width, height), top), image)
    ImageDraw.Draw(image).text((16, 16), f"stub, seed {job.seed}\n{job.prompt[:200]}", fill=(240, 240, 240))
    return image


class StubBackendGateway(ImageBackendGateway):
    # A step outlasts the page's 800 ms progress poll, as on the real engines.
    # Faster steps fall between polls, and the page never learns a step rate.
    def __init__(self, capabilities: Capabilities, seconds_per_step: float = 1.0):
        self._capabilities = capabilities
        self._seconds_per_step = seconds_per_step

    def capabilities(self) -> Capabilities:
        return self._capabilities

    def load(self) -> None:
        pass

    def run(self, job, on_step, should_stop) -> ImageResult:
        total = steps_to_run(job)
        for step in range(1, total + 1):
            time.sleep(self._seconds_per_step)
            if should_stop():
                raise Cancelled(f"stopped at step {step}")
            on_step(step, total)
        width, height = image_size(job)
        return ImageResult(
            png=to_png(placeholder(job, width, height)),
            width=width,
            height=height,
            seed=job.seed,
            steps=int(job.options["steps"]),
        )

    def release(self) -> None:
        pass
