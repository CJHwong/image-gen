"""The mflux half of qwen21: the form mapped to generate_image, and the model's life."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.mflux_runtime import StepHook
from studio.l3_interface_adapters.gateways.qwen21 import generator as generator_module
from studio.l3_interface_adapters.gateways.qwen21.generator import Qwen21Generator, build_model, generate_kwargs
from tests.support.heavy import heavy_modules
from tests.support.images import png


def job(mode="generate", references=(), **options):
    defaults = {"size": "1024x1024", "steps": 8, "guidance": 1.0, "strength": 0.4, "negative": ""}
    return ImageJob(mode=mode, prompt="a pear", seed=5, options={**defaults, **options}, references=references)


def never_stop():
    return False


def no_steps(step, total):
    pass


def test_generate_maps_the_form_to_mflux():
    kwargs = generate_kwargs(job(size="768x432", negative="blur", guidance=2.5))
    assert kwargs == {
        "seed": 5,
        "prompt": "a pear",
        "negative_prompt": "blur",
        "width": 768,
        "height": 432,
        "num_inference_steps": 8,
        "guidance": 2.5,
    }


def test_a_reference_brings_its_strength_and_is_passed_as_an_image():
    kwargs = generate_kwargs(job(references=(png(64, 48),), strength=0.6))
    assert kwargs["image_strength"] == 0.6
    assert kwargs["image_path"].size == (64, 48)


def test_match_keeps_the_reference_shape_at_one_megapixel():
    kwargs = generate_kwargs(job(references=(png(1600, 900),), size="match"))
    assert (kwargs["width"], kwargs["height"]) == (1360, 768)
    assert generate_kwargs(job(size="match"))["width"] == 1024  # no reference: the square default


LIVE_ENCODER = object()  # stands in for the 17.5 GB Qwen3-VL text encoder while it is resident


class FakeEngine:
    """An mflux model stand-in. It records the kwargs and reports steps like the real loop."""

    def __init__(self, hook=None, text_encoder=LIVE_ENCODER, cache=()):
        self.hook = hook
        self.text_encoder = text_encoder
        self.prompt_cache = dict.fromkeys(cache)
        self.kwargs = None

    def generate_image(self, **kwargs):
        self.kwargs = kwargs
        for index in range(kwargs["num_inference_steps"]):
            if self.hook is not None:
                self.hook.call_in_loop(index, None, None, None, None, None)
        return SimpleNamespace(image=Image.new("RGB", (kwargs["width"], kwargs["height"])))


class EngineBuilder:
    """A build stand-in: it hands out one engine per call and keeps the ones it built."""

    def __init__(self, engines):
        self.pending = list(engines)
        self.built = []

    def __call__(self, quantize, hook):
        engine = self.pending.pop(0)
        engine.hook = hook
        self.built.append(engine)
        return engine


def test_the_model_is_built_with_the_memory_saver_and_the_step_hook():
    """MemorySaver drops the 17.5 GB text encoder before the loop, which is why a run
    peaks at 30.68 GB instead of 45.01 GB. The hook is registered once, not per run."""
    registered = []

    class FakeCallbacks:
        def register(self, callback):
            registered.append(callback)

    class FakeQwenImage21:
        def __init__(self, quantize):
            self.quantize = quantize
            self.callbacks = FakeCallbacks()

    memory_saver = Mock(return_value="the memory saver")
    with heavy_modules(
        {
            "mflux.callbacks.instances.memory_saver": {"MemorySaver": memory_saver},
            "mflux.models.qwen21.variants.txt2img.qwen_image_21": {"QwenImage21": FakeQwenImage21},
        }
    ):
        hook = StepHook()
        model = build_model(quantize=8, hook=hook)

    assert model.quantize == 8
    assert registered == ["the memory saver", hook]
    assert memory_saver.call_args.kwargs == {
        "model": model,
        "keep_transformer": True,
        "cache_limit_bytes": None,
        "num_seeds": 1,
    }


def test_the_model_is_built_once_and_kept_for_the_next_run():
    builder = EngineBuilder([FakeEngine(), FakeEngine()])
    generator = Qwen21Generator(quantize=None, build=builder)
    generator.load()
    generator.load()
    generator.run(job(), no_steps, never_stop)
    assert len(builder.built) == 1  # the second engine was never needed
    assert builder.built[0].kwargs is not None


def test_a_run_reports_every_step_and_returns_the_image():
    builder = EngineBuilder([FakeEngine()])
    generator = Qwen21Generator(quantize=None, build=builder)
    reported = []
    result = generator.run(job(size="640x384", steps=3), lambda step, total: reported.append((step, total)), never_stop)

    # Step 0 says the engine started, the way the edit child does, so the page can
    # show the load until it and the prompt reading after it.
    assert reported == [(0, 3), (1, 3), (2, 3), (3, 3)]
    assert builder.built[0].kwargs["width"] == 640 and builder.built[0].kwargs["num_inference_steps"] == 3
    assert (result.width, result.height, result.seed, result.steps) == (640, 384, 5, 3)
    assert result.png[:4] == b"\x89PNG"


def test_a_cancel_leaves_the_loop_and_still_frees_the_buffers(monkeypatch):
    """The release sits in a finally, so a cancelled run gives its 22.42 GB back too."""
    freed = Mock()
    monkeypatch.setattr(generator_module, "release_mlx_buffers", freed)
    generator = Qwen21Generator(quantize=None, build=EngineBuilder([FakeEngine()]))
    reported = []

    def on_step(step, total):
        reported.append(step)

    def stop_after_two():
        return len(reported) >= 2

    with pytest.raises(Cancelled, match="stopped at step 2"):
        generator.run(job(steps=3), on_step, stop_after_two)
    assert reported == [0, 1] and freed.call_count == 1


def test_a_cached_prompt_does_not_rebuild_the_model():
    """MemorySaver drops the text encoder before every loop, so after the first image it
    is gone. Rebuilding costs 1.0s where the image costs 40s, so the cache saves that."""
    cached = ("a pear",)
    builder = EngineBuilder([FakeEngine(text_encoder=None, cache=cached), FakeEngine(text_encoder=None, cache=cached)])
    generator = Qwen21Generator(quantize=None, build=builder)
    generator.run(job(), no_steps, never_stop)
    generator.run(job(), no_steps, never_stop)
    assert len(builder.built) == 1


def test_an_uncached_prompt_rebuilds_the_model():
    """Rebuilding costs 1.0s against 40s for the image, so the model is rebuilt rather
    than run without the encoder its prompt still needs."""
    builder = EngineBuilder([FakeEngine(text_encoder=None), FakeEngine(text_encoder=None)])
    generator = Qwen21Generator(quantize=None, build=builder)
    generator.run(job(), no_steps, never_stop)
    assert len(builder.built) == 2
    assert builder.built[0].kwargs is None  # the encoder-less model never ran
    assert builder.built[1].kwargs["prompt"] == "a pear"


def test_a_true_cfg_run_rebuilds_for_the_negative_prompt_it_will_encode():
    """mflux encodes the negative prompt only when guidance is above 1, so the same
    cached prompt needs a rebuild in that case and in no other."""
    cached = ("a pear",)
    builder = EngineBuilder([FakeEngine(text_encoder=None, cache=cached), FakeEngine(text_encoder=None, cache=cached)])
    generator = Qwen21Generator(quantize=None, build=builder)
    generator.run(job(negative="blur", guidance=1.0), no_steps, never_stop)
    assert len(builder.built) == 1
    generator.run(job(negative="blur", guidance=2.5), no_steps, never_stop)
    assert len(builder.built) == 2 and builder.built[1].kwargs["negative_prompt"] == "blur"
