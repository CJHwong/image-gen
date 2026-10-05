"""The edit half of qwen21: the form mapped to generate_image, and the model's life.

Editing runs on mflux in this process, so these tests stub the engine the way the
generator tests do. The one thing that differs is the references: the edit call
takes paths, so a run writes them and removes them, and that is asserted here.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.mflux_runtime import StepHook
from studio.l3_interface_adapters.gateways.qwen21 import edit as edit_module
from studio.l3_interface_adapters.gateways.qwen21.capabilities import EDIT_MATCH_CAP
from studio.l3_interface_adapters.gateways.qwen21.edit import (
    GRID,
    Qwen21Edit,
    build_model,
    edit_kwargs,
    edit_resolution,
    on_the_grid,
)
from tests.support.heavy import heavy_modules
from tests.support.images import png


def job(mode="edit", references=(), **options):
    defaults = {"resolution": "match", "steps": 8, "cfg": 1.0, "negative": ""}
    return ImageJob(mode=mode, prompt="a pear", seed=5, options={**defaults, **options}, references=references)


def never_stop():
    return False


def no_steps(step, total):
    pass


def test_an_area_budget_lands_on_the_grid_mflux_accepts():
    """mflux refuses an output_resolution that is not a multiple of 32, before the
    model loads. The page's own figure is the square root of a pixel count, which
    is almost never one."""
    assert on_the_grid(1024) == 1024
    assert on_the_grid(1000) == 992
    assert on_the_grid(100) == 96
    assert GRID == 32


def test_an_area_budget_never_rounds_down_to_nothing():
    assert on_the_grid(10) == 32 and on_the_grid(0) == 32


def test_match_follows_the_last_reference_and_stops_at_the_cap():
    """The last reference is the picture, or the marked region the page appends
    after it, and the page writes that region at the picture's own size, so both
    give the same area."""
    assert edit_resolution(job(references=(png(512, 512),))) == 512
    assert edit_resolution(job(references=(png(32, 32), png(2560, 1440)))) == EDIT_MATCH_CAP


def test_a_chosen_area_is_passed_through():
    assert edit_resolution(job(references=(png(32, 32),), resolution="768")) == 768


def test_guidance_above_one_without_a_negative_is_refused():
    """mflux refuses this pair and the page can reach it: the scale is a field the
    user may raise by hand. The refusal names the control rather than arriving as an
    engine error after a 33 GB load."""
    with pytest.raises(InvalidJob, match="guidance above 1 needs a negative prompt"):
        edit_kwargs(job(references=(png(32, 32),), cfg=2.5), [])


def test_the_edit_maps_the_form_to_mflux():
    kwargs = edit_kwargs(
        job(references=(png(32, 32),), resolution="768", steps=12, cfg=2.5, negative="blur"), ["a.png"]
    )
    assert kwargs == {
        "seed": 5,
        "prompt": "a pear",
        "negative_prompt": "blur",
        "guidance": 2.5,
        "num_inference_steps": 12,
        "image_paths": ["a.png"],
        "output_resolution": 768,
    }


def test_a_blank_negative_reaches_mflux_as_none():
    """mflux skips the negative pass only when guidance is 1 and the prompt is None."""
    assert edit_kwargs(job(references=(png(32, 32),)), [])["negative_prompt"] is None


def test_a_mode_that_offers_no_guidance_still_maps():
    """Viggle Turbo's edit declares no cfg and no negative prompt, because the
    distillation was trained without classifier-free guidance, so the form never
    carries them. The adapter has to take the engine's own defaults instead. This
    raised KeyError until that backend was run for real."""
    bare = ImageJob(
        mode="edit",
        prompt="a pear",
        seed=5,
        options={"resolution": "match", "steps": 6},
        references=(png(32, 32),),
    )
    kwargs = edit_kwargs(bare, [])
    assert kwargs["guidance"] == 1.0 and kwargs["negative_prompt"] is None
    assert kwargs["num_inference_steps"] == 6


def test_the_model_is_built_with_the_step_hook():
    """The hook is registered once, when the model is built, because
    CallbackRegistry.register appends and never dedups."""
    registered = []

    class FakeCallbacks:
        def register(self, callback):
            registered.append(callback)

    class FakeQwenImage21Edit:
        def __init__(self, quantize):
            self.quantize = quantize
            self.callbacks = FakeCallbacks()

    with heavy_modules(
        {"mflux.models.qwen21.variants.edit.qwen_image_21_edit": {"QwenImage21Edit": FakeQwenImage21Edit}}
    ):
        hook = StepHook()
        model = build_model(quantize=8, hook=hook)

    assert model.quantize == 8 and registered == [hook]


class FakeEngine:
    """An mflux edit model stand-in. It records the kwargs and reads every path it is
    given, so a test can tell that the references were on disk for the call."""

    def __init__(self, hook=None):
        self.hook = hook
        self.kwargs = None
        self.read: list[tuple[str, bytes]] = []

    def generate_image(self, **kwargs):
        self.kwargs = kwargs
        self.read = [(path, Path(path).read_bytes()) for path in kwargs["image_paths"]]
        for index in range(kwargs["num_inference_steps"]):
            if self.hook is not None:
                self.hook.call_in_loop(index, None, None, None, None, None)
        return SimpleNamespace(image=Image.new("RGB", (kwargs["output_resolution"],) * 2))


class EngineBuilder:
    """A build stand-in: it hands out one engine per call and keeps the ones it built."""

    def __init__(self, engines):
        self.pending = list(engines)
        self.built = []

    def __call__(self, quantize, hook, lora_path=None):
        engine = self.pending.pop(0)
        engine.hook = hook
        engine.lora_path = lora_path
        self.built.append(engine)
        return engine


def test_the_model_is_built_once_and_kept_for_the_next_run():
    builder = EngineBuilder([FakeEngine(), FakeEngine()])
    edit = Qwen21Edit(quantize=None, build=builder)
    edit.load()
    edit.load()
    edit.run(job(references=(png(32, 32),)), no_steps, never_stop)
    assert len(builder.built) == 1  # the second engine was never needed


def test_a_run_writes_the_references_for_the_call_and_removes_them_after():
    """mflux's edit call takes image_paths, not images, so this is the one path in
    the server that puts a reference on disk. The directory lives for one run."""
    source = png(64, 48)
    builder = EngineBuilder([FakeEngine()])
    edit = Qwen21Edit(quantize=None, build=builder)

    edit.run(job(references=(source, source)), no_steps, never_stop)

    assert [content for _, content in builder.built[0].read] == [source.png, source.png]
    assert not any(Path(path).exists() for path, _ in builder.built[0].read)


def test_a_run_reports_every_step_and_returns_the_image():
    builder = EngineBuilder([FakeEngine()])
    edit = Qwen21Edit(quantize=None, build=builder)
    reported = []
    result = edit.run(
        job(references=(png(32, 32),), resolution="768", steps=3), lambda s, t: reported.append((s, t)), never_stop
    )

    # Step 0 says the model started, so the page can show the load and the encode
    # after it, which is the longest part of an edit and reports no steps.
    assert reported == [(0, 3), (1, 3), (2, 3), (3, 3)]
    assert builder.built[0].kwargs["output_resolution"] == 768
    assert (result.width, result.height, result.seed, result.steps) == (768, 768, 5, 3)
    assert result.png[:4] == b"\x89PNG"


def test_a_cancel_leaves_the_loop_and_still_frees_the_buffers(monkeypatch):
    freed = Mock()
    monkeypatch.setattr(edit_module, "release_mlx_buffers", freed)
    stopped = False

    def should_stop():
        return stopped

    class Stopping(FakeEngine):
        def generate_image(self, **kwargs):
            nonlocal stopped
            stopped = True
            return super().generate_image(**kwargs)

    builder = EngineBuilder([Stopping()])
    edit = Qwen21Edit(quantize=None, build=builder)
    with pytest.raises(Cancelled, match="stopped at step 1"):
        edit.run(job(references=(png(32, 32),), steps=8), no_steps, should_stop)
    assert freed.call_count == 1


def test_release_drops_the_model_and_frees_the_buffers(monkeypatch):
    freed = Mock()
    monkeypatch.setattr(edit_module, "release_mlx_buffers", freed)
    builder = EngineBuilder([FakeEngine(), FakeEngine()])
    edit = Qwen21Edit(quantize=None, build=builder)
    edit.load()
    edit.release()
    assert freed.call_count == 1
    edit.load()
    assert len(builder.built) == 2  # the model was rebuilt after the release
