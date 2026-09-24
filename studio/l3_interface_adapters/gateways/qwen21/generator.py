"""Qwen-Image-2.1 text-to-image and image-to-image, through mflux, in this process.

mflux memory-maps the weights, so a resident model is not measurably faster than
a fresh CLI run: the same 8-step 1024 image took 30.2s through the CLI and 31s
here. The model stays resident for the text encoder cache, not for speed.
"""

from collections.abc import Callable

from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.image_sizes import match_reference_size
from studio.l3_interface_adapters.gateways.mflux_runtime import StepHook, release_mlx_buffers
from studio.l3_interface_adapters.gateways.png_images import to_pil, to_png
from studio.l3_interface_adapters.gateways.qwen21.capabilities import MATCH


def generate_kwargs(job: ImageJob) -> dict:
    """The job as generate_image keyword arguments.

    mflux's generate_image takes a single image_path, so only the first
    reference is used. It is passed as a PIL image, never as a file.
    """
    options = job.options
    reference = job.references[0] if job.references else None
    if options["size"] != MATCH:
        width, height = (int(side) for side in str(options["size"]).split("x"))
    elif reference is not None:
        width, height = match_reference_size(reference.width, reference.height)
    else:
        width, height = 1024, 1024
    kwargs = {
        "seed": job.seed,
        "prompt": job.prompt,
        "negative_prompt": options["negative"] or None,
        "width": width,
        "height": height,
        "num_inference_steps": options["steps"],
        "guidance": options["guidance"],
    }
    if reference is not None:
        kwargs["image_path"] = to_pil(reference.png)
        kwargs["image_strength"] = options["strength"]
    return kwargs


def build_model(quantize, hook: StepHook):
    """Build the model and register mflux's MemorySaver and the step hook.

    MemorySaver drops the 17.5 GB Qwen3-VL text encoder before the denoising
    loop. The encoder is dead weight once the prompt is encoded. Measured at
    1024, four generations each:

        without   peak 45.01 GB   active 30.39 GB   cache 22.42 GB
        with      peak 30.68 GB   active 15.25 GB   cache  0.00 GB

    30.68 GB is exactly what the CLI reports for the same image.
    """
    from mflux.callbacks.instances.memory_saver import MemorySaver
    from mflux.models.qwen21.variants.txt2img.qwen_image_21 import QwenImage21

    model = QwenImage21(quantize=quantize)
    model.callbacks.register(MemorySaver(model=model, keep_transformer=True, cache_limit_bytes=None, num_seeds=1))
    model.callbacks.register(hook)
    return model


class Qwen21Generator:
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
        kwargs = generate_kwargs(job)
        model = self._with_encoder(self._loaded(), kwargs)
        steps = kwargs["num_inference_steps"]
        on_step(0, steps)
        try:
            with self._hook.watch(on_step, should_stop, steps):
                image = model.generate_image(**kwargs).image
        finally:
            release_mlx_buffers()
        return ImageResult(png=to_png(image), width=image.width, height=image.height, seed=job.seed, steps=steps)

    def _with_encoder(self, model, kwargs: dict):
        """Put the text encoder back when this prompt needs it.

        MemorySaver drops the encoder before every denoising loop, so after the
        first image it is gone. A prompt already in model.prompt_cache does not
        need it. Anything else does, and rebuilding the model is the only way
        back: 1.0s against 40s for the image. A batch reuses one prompt, so it
        pays nothing.
        """
        if model.text_encoder is not None:
            return model
        needed = [kwargs["prompt"]]
        # mflux encodes the negative prompt only when true CFG is on
        if kwargs["negative_prompt"] and kwargs["guidance"] > 1.0:
            needed.append(kwargs["negative_prompt"])
        if all(text in model.prompt_cache for text in needed):
            return model
        self.release()
        return self._loaded()
