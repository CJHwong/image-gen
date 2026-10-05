"""Qwen-Image-2.1 instruction editing, through mflux in this process.

mflux 0.21.0 ported the Qwen3-VL vision tower, so editing runs on the same MLX
engine as generation and needs no child process. What that replaced: a diffusers
pipeline in a stdio child, a 20 to 36 second build that had to stay up between
edits, and 38.7 GiB held on MPS, which did not fit beside the mflux model. The
two engines had to free each other. PORTABILITY.md records what the change buys.

This is the only path in the server that writes a reference to disk. mflux's
edit call takes image_paths, not images, so a reference cannot stay in memory
here the way it does on the generate side. The directory lives for one run.
"""

import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.mflux_runtime import StepHook, release_mlx_buffers
from studio.l3_interface_adapters.gateways.png_images import to_png
from studio.l3_interface_adapters.gateways.qwen21.capabilities import EDIT_MATCH_CAP, MATCH

# mflux holds the area budget to a multiple of 32. The page's "match" figure is
# the square root of the reference's pixel count, which is almost never one.
GRID = 32


def on_the_grid(resolution: float) -> int:
    """The nearest area budget mflux accepts, never below one tile."""
    return max(GRID, GRID * round(resolution / GRID))


def edit_resolution(job: ImageJob) -> int:
    """The pixel area this run aims at.

    "Match" follows the last reference. That is the picture, or the marked region
    the page appends after it, which the page writes at the picture's own size,
    so both give the same area. mflux sizes the output from the last reference
    and this number only sets how many pixels go into it.
    """
    if job.options["resolution"] != MATCH:
        return int(str(job.options["resolution"]))
    last = job.references[-1]
    return min(on_the_grid((last.width * last.height) ** 0.5), EDIT_MATCH_CAP)


def edit_kwargs(job: ImageJob, image_paths: list[str]) -> dict:
    """The job as QwenImage21Edit.generate_image keyword arguments.

    Every reference goes in, the marked region included. That region is an
    opaque image whose colours name the areas, and the sentence the page sends
    names the area by its colour, so it is a reading aid rather than a latent
    mask. mflux's own mask_image is a hard inpaint over the first reference, and
    it is not what the page asks for.
    """
    options = job.options
    guidance = float(options["cfg"])
    negative = str(options["negative"])
    if guidance > 1 and not negative:
        # mflux refuses this pair, and the page can reach it: the scale is a field
        # the user may raise by hand. Refuse here, so the message names the control
        # instead of arriving as an engine error after the model has loaded.
        raise InvalidJob("guidance above 1 needs a negative prompt. Type one, or set guidance back to 1.")
    return {
        "seed": job.seed,
        "prompt": job.prompt,
        "negative_prompt": negative or None,
        "guidance": guidance,
        "num_inference_steps": int(options["steps"]),
        "image_paths": image_paths,
        "output_resolution": edit_resolution(job),
    }


@contextmanager
def written(references):
    """The references as paths, for the length of one call.

    mflux's edit call takes image_paths, not images, so this is the only place in
    the server that puts a reference on disk. The directory goes on the way out,
    whether the run answered or raised.
    """
    with tempfile.TemporaryDirectory(prefix="studio-edit-") as directory:
        paths = [str(Path(directory) / f"{index}.png") for index in range(len(references))]
        for reference, path in zip(references, paths, strict=True):
            Path(path).write_bytes(reference.png)
        yield paths


def build_model(quantize, hook: StepHook):
    """Build the edit model and register the step hook.

    The edit variant loads the vision tower the text-to-image variant does not,
    so the two models do not both fit on a 64 GB machine and the gateway frees
    one for the other.
    """
    from mflux.models.qwen21.variants.edit.qwen_image_21_edit import QwenImage21Edit

    model = QwenImage21Edit(quantize=quantize)
    model.callbacks.register(hook)
    return model


class Qwen21Edit:
    def __init__(self, quantize: int | None, build: Callable = build_model):
        self._quantize = quantize
        self._build = build
        self._hook = StepHook()
        self._model = None

    def load(self) -> None:
        self._loaded()

    def _loaded(self):
        if self._model is None:
            self._model = self._build(self._quantize, self._hook)
        return self._model

    def release(self) -> None:
        self._model = None
        release_mlx_buffers()

    def run(self, job: ImageJob, on_step, should_stop) -> ImageResult:
        steps = int(job.options["steps"])
        with written(job.references) as paths:
            # The form is checked before the model loads, so a bad value does not
            # cost a 33 GB build first.
            kwargs = edit_kwargs(job, paths)
            model = self._loaded()
            on_step(0, steps)
            image = self._render(model, kwargs, on_step, should_stop, steps)
        return ImageResult(png=to_png(image), width=image.width, height=image.height, seed=job.seed, steps=steps)

    def _render(self, model, kwargs: dict, on_step, should_stop, steps: int):
        """One pass through the engine, with the buffers handed back either way."""
        try:
            with self._hook.watch(on_step, should_stop, steps):
                return model.generate_image(**kwargs).image
        finally:
            release_mlx_buffers()
