"""FLUX.2 klein-base-9B through mflux, in this process: Flux2Klein for generate,
Flux2KleinEdit for edit.

Both load the same transformer, so only one is kept: a run in the other mode
frees the first. mflux reads the weights lazily, so building a model takes
under a second, and the first run pays the load.

The model dir holds a diffusers-layout klein-base-9b. `base_model` tells mflux
which config to use, since a local path does not name one it knows. The
README at the repo root has the download recipe.
"""

from collections.abc import Callable

from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.flux2.capabilities import MATCH
from studio.l3_interface_adapters.gateways.image_sizes import match_reference_size
from studio.l3_interface_adapters.gateways.mflux_runtime import StepHook, release_mlx_buffers
from studio.l3_interface_adapters.gateways.png_images import to_pil, to_png

BASE_MODEL = "flux2-klein-base-9b"
REGISTRY_KEY = "flux2-klein-4b"  # gitleaks:allow (an mflux model name, not a secret)


def image_size(job: ImageJob) -> tuple[int, int]:
    """The chosen size, or the last reference's shape at about 1 MP."""
    size = job.options["size"]
    if size != MATCH:
        width, height = (int(side) for side in str(size).split("x"))
        return width, height
    if job.references:
        reference = job.references[-1]
        return match_reference_size(reference.width, reference.height)
    return 1024, 1024


def generate_kwargs(job: ImageJob) -> dict:
    """The job as Flux2Klein.generate_image arguments. It takes one reference."""
    width, height = image_size(job)
    kwargs = {
        "seed": job.seed,
        "prompt": job.prompt,
        "width": width,
        "height": height,
        "num_inference_steps": job.options["steps"],
        "guidance": job.options["guidance"],
    }
    if job.references:
        kwargs["image_path"] = to_pil(job.references[0].png)
        kwargs["image_strength"] = job.options["strength"]
    return kwargs


def edit_kwargs(job: ImageJob) -> dict:
    """The job as Flux2KleinEdit.generate_image arguments, every reference as a PIL image."""
    width, height = image_size(job)
    return {
        "seed": job.seed,
        "prompt": job.prompt,
        "width": width,
        "height": height,
        "num_inference_steps": job.options["steps"],
        "guidance": job.options["guidance"],
        "image_paths": [to_pil(reference.png) for reference in job.references],
    }


def build_model(mode: str, model_dir: str, quantize: int | None, hook: StepHook):
    from mflux.models.common.config.model_config import AVAILABLE_MODELS
    from mflux.models.common.resolution.config_resolution import ConfigResolution
    from mflux.models.flux2.variants import Flux2Klein, Flux2KleinEdit

    # The same call the mflux flux2 CLIs make: the klein family keyed on its
    # default entry, with the local weights declared as the base model.
    family = tuple(key for key in AVAILABLE_MODELS if key.startswith("flux2-") and key != REGISTRY_KEY)
    config = ConfigResolution.resolve_restricted(
        None, REGISTRY_KEY, model_path=model_dir, extra_keys=family, base_model=BASE_MODEL
    )
    variant = Flux2KleinEdit if mode == "edit" else Flux2Klein
    model = variant(model_config=config, quantize=quantize, model_path=model_dir)
    model.callbacks.register(hook)
    return model


class KleinModels:
    def __init__(self, model_dir: str, quantize: int | None, build: Callable = build_model):
        self._model_dir = model_dir
        self._quantize = quantize
        self._build = build
        self._hook = StepHook()
        self._model = None
        self._mode = None

    def load(self, mode: str = "generate") -> None:
        self._loaded(mode)

    def _loaded(self, mode: str):
        if self._model is None or self._mode != mode:
            self.release()
            self._model = self._build(mode, self._model_dir, self._quantize, self._hook)
            self._mode = mode
        return self._model

    def release(self) -> None:
        self._model = None
        self._mode = None
        release_mlx_buffers()

    def run(self, job: ImageJob, on_step, should_stop) -> ImageResult:
        kwargs = edit_kwargs(job) if job.mode == "edit" else generate_kwargs(job)
        model = self._loaded(job.mode)
        steps = kwargs["num_inference_steps"]
        on_step(0, steps)
        try:
            with self._hook.watch(on_step, should_stop, steps):
                image = model.generate_image(**kwargs).image
        finally:
            release_mlx_buffers()
        return ImageResult(png=to_png(image), width=image.width, height=image.height, seed=job.seed, steps=steps)
