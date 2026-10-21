"""Qwen-Image-2.1 text-to-image and image-to-image, through mflux, in this process.

mflux memory-maps the weights, so a resident model is not measurably faster than
a fresh CLI run: the same 8-step 1024 image took 30.2s through the CLI and 31s
here. The model stays resident for the text encoder cache, not for speed.
"""

from collections.abc import Callable

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.image_sizes import match_reference_size
from studio.l3_interface_adapters.gateways.mflux_runtime import StepHook, lora_kwargs, release_mlx_buffers
from studio.l3_interface_adapters.gateways.png_images import to_pil, to_png
from studio.l3_interface_adapters.gateways.qwen_image_controls import MATCH


def generate_kwargs(job: ImageJob, scheduler: str = "linear") -> dict:
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
        # A mode does not have to declare these. One distilled to run without
        # guidance offers neither a scale nor a negative prompt, so `parse_options`
        # leaves both out, and the engine's own default is what that means.
        "negative_prompt": options.get("negative") or None,
        "width": width,
        "height": height,
        "num_inference_steps": options["steps"],
        "guidance": options.get("guidance", 1.0),
        "scheduler": scheduler,
    }
    if reference is not None:
        kwargs["image_path"] = to_pil(reference.png)
        kwargs["image_strength"] = options["strength"]
    return kwargs


def build_model(quantize, hook: StepHook, lora_path: str | None = None, model_path: str | None = None):
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

    if model_path is None:
        model = QwenImage21(quantize=quantize, **lora_kwargs(lora_path))
    else:
        from studio.l3_interface_adapters.gateways.mflux_runtime import official_turbo_model_config

        model = QwenImage21(
            quantize=quantize,
            model_path=model_path,
            model_config=official_turbo_model_config(),
            **lora_kwargs(lora_path),
        )
    model.callbacks.register(MemorySaver(model=model, keep_transformer=True, cache_limit_bytes=None, num_seeds=1))
    model.callbacks.register(hook)
    return model


class Qwen21Generator:
    def __init__(
        self,
        quantize: int | None,
        build: Callable = build_model,
        lora_path: str | None = None,
        scheduler: str = "linear",
        model_path: str | None = None,
        restore_encoder: Callable | None = None,
    ):
        self._quantize = quantize
        self._build = build
        self._lora_path = lora_path
        self._scheduler = scheduler
        self._model_path = model_path
        self._restore_encoder = restore_encoder
        self._hook = StepHook()
        self._model = None

    def load(self) -> None:
        self._loaded()

    def _loaded(self):
        if self._model is None:
            if self._model_path is None:
                self._model = self._build(self._quantize, self._hook, self._lora_path)
            else:
                self._model = self._build(self._quantize, self._hook, self._lora_path, model_path=self._model_path)
        return self._model

    def release(self) -> None:
        self._model = None
        release_mlx_buffers()

    def prepare_batch(self, jobs: list[ImageJob], should_stop: Callable[[], bool]) -> None:
        if not jobs:
            return
        _check_cancel(should_stop)
        prompts = _batch_prompts(jobs, self._scheduler)
        model = self._loaded()
        if model.text_encoder is None and not all(prompt in model.prompt_cache for prompt in prompts):
            if self._restore_encoder is not None:
                self._restore_encoder(model)
            else:
                # Release the old reference before a rebuild allocates another transformer.
                model = None
                self.release()
                model = self._loaded()
        try:
            for prompt in prompts:
                _check_cancel(should_stop)
                if prompt not in model.prompt_cache:
                    _cache_prompt(model, prompt)
        finally:
            release_mlx_buffers()

    def run(self, job: ImageJob, on_step, should_stop) -> ImageResult:
        kwargs = generate_kwargs(job, self._scheduler)
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
        need it. The measured Turbo restore loads only the encoder. Other
        backends keep the full rebuild. Batch preparation encodes its known
        prompts before the first denoising loop.
        """
        if model.text_encoder is not None:
            return model
        needed = [kwargs["prompt"]]
        # mflux encodes the negative prompt only when true CFG is on
        if kwargs["negative_prompt"] and kwargs["guidance"] > 1.0:
            needed.append(kwargs["negative_prompt"])
        if all(text in model.prompt_cache for text in needed):
            return model
        if self._restore_encoder is not None:
            self._restore_encoder(model)
            return model
        # The frame names the old model, so the rebuild below would allocate a second
        # copy of the weights while the first is still live. Dropping the name lets the
        # release collect it before the new one is built. Measured 2026-10-06 on three
        # prompts at 768 x 768 in one process: the peak read 16.9 + 30.7 = 47.6 GB with
        # the name held, and 30.7 GB, the weights alone, without it. The active memory
        # also held at 16.9 GB across the three instead of climbing to 32.2 GB, and the
        # same growth reached 64.4 GB over a 35 image sample on a 64 GB machine.
        #
        # It is also the faster arm, and by more than the copy costs. Alternating the
        # two in one process over twelve images, with the order reversed in half the
        # pairs so the machine's own drift lands on both, this side averaged 14.8s an
        # image against 21.5s, and all six pairs read the same way.
        model = None
        self.release()
        return self._loaded()


def _batch_prompts(jobs: list[ImageJob], scheduler: str) -> list[str]:
    prompts = {}
    for job in jobs:
        kwargs = generate_kwargs(job, scheduler)
        prompts[kwargs["prompt"]] = None
        if kwargs["negative_prompt"] and kwargs["guidance"] > 1.0:
            prompts[kwargs["negative_prompt"]] = None
    return list(prompts)


def _cache_prompt(model, prompt: str) -> None:
    import mlx.core as mx
    from mflux.models.qwen21.model.qwen21_text_encoder.qwen21_prompt_encoder import Qwen21PromptEncoder

    embeddings = Qwen21PromptEncoder.encode_prompt(
        prompt, model.prompt_cache, model.tokenizers["qwen21"], model.text_encoder
    )
    mx.eval(*embeddings)


def _check_cancel(should_stop: Callable[[], bool]) -> None:
    if should_stop():
        raise Cancelled("The image batch was cancelled during prompt encoding.")
