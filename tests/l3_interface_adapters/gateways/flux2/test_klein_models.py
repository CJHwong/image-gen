from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.flux2.klein_models import (
    BASE_MODEL,
    KleinModels,
    build_model,
    edit_kwargs,
    generate_kwargs,
    image_size,
)
from studio.l3_interface_adapters.gateways.mflux_runtime import StepHook
from tests.support.heavy import heavy_modules
from tests.support.images import png


def job(mode="generate", references=(), **options):
    defaults = {"size": "1024x1024", "steps": 8, "guidance": 4.0}
    if mode == "generate":
        defaults["strength"] = 0.4
    return ImageJob(mode=mode, prompt="a pear", seed=5, options={**defaults, **options}, references=references)


class FakeModel:
    """A variant that records the mode it was built for and the arguments it ran with."""

    def __init__(self, mode, runs):
        self.mode, self.runs = mode, runs

    def generate_image(self, **kwargs):
        self.runs.append((self.mode, kwargs))
        return SimpleNamespace(image=Image.new("RGB", (kwargs["width"], kwargs["height"])))


class Recording:
    """The `build` callable KleinModels takes, and what it was asked for."""

    def __init__(self):
        self.builds = []
        self.runs = []

    def build(self, mode, *_):
        self.builds.append(mode)
        return FakeModel(mode, self.runs)

    def models(self):
        return KleinModels("dir", 8, build=self.build)


def run(models, the_job, seen):
    """Run one job and record every step the page would have been told."""
    return models.run(the_job, lambda step, total: seen.append((step, total)), lambda: False)


def test_generate_maps_the_form_to_mflux():
    assert generate_kwargs(job(size="1280x720", guidance=2.5)) == {
        "seed": 5,
        "prompt": "a pear",
        "width": 1280,
        "height": 720,
        "num_inference_steps": 8,
        "guidance": 2.5,
    }


def test_a_generate_reference_brings_its_strength():
    # Flux2Klein takes one image_path, and the strength is the share of the
    # schedule it keeps. Without it the reference is ignored.
    kwargs = generate_kwargs(job(references=(png(64, 48),), strength=0.6))
    assert kwargs["image_strength"] == 0.6
    assert kwargs["image_path"].size == (64, 48)


def test_edit_passes_every_reference_and_matches_the_last_shape():
    kwargs = edit_kwargs(job("edit", references=(png(32, 32), png(1600, 900)), size="match"))
    assert [image.size for image in kwargs["image_paths"]] == [(32, 32), (1600, 900)]
    assert (kwargs["width"], kwargs["height"]) == (1360, 768)
    assert "image_strength" not in kwargs


def test_a_generate_without_a_size_asks_for_one_megapixel():
    # "match" with nothing to match falls back to a square. A zero side would be
    # a refused run.
    assert image_size(job(size="match", references=())) == (1024, 1024)


def test_the_model_is_built_from_the_local_weights_with_the_klein_family():
    # A local path does not name a config mflux knows, so the call declares the
    # klein family and the base model, as the mflux flux2 CLIs do.
    klein, klein_edit = Mock(), Mock()
    resolve = Mock(return_value="the config")
    registry = {"flux2-klein-4b": 1, "flux2-klein-base-9b": 2, "flux2-dev": 3, "qwen-image": 4}
    with heavy_modules(
        {
            "mflux.models.common.config.model_config": {"AVAILABLE_MODELS": registry},
            "mflux.models.common.resolution.config_resolution": {"ConfigResolution": Mock(resolve_restricted=resolve)},
            "mflux.models.flux2.variants": {"Flux2Klein": klein, "Flux2KleinEdit": klein_edit},
        }
    ):
        hook = StepHook()
        model = build_model("generate", "/weights/klein", 8, hook)

    assert resolve.call_args.kwargs == {
        "model_path": "/weights/klein",
        "extra_keys": ("flux2-klein-base-9b", "flux2-dev"),  # the family, without the key mflux resolves on
        "base_model": BASE_MODEL,
    }
    assert klein.call_args.kwargs == {"model_config": "the config", "quantize": 8, "model_path": "/weights/klein"}
    klein_edit.assert_not_called()
    assert model is klein.return_value
    klein.return_value.callbacks.register.assert_called_once_with(hook)


def test_an_edit_builds_the_edit_variant():
    klein, klein_edit = Mock(), Mock()
    with heavy_modules(
        {
            "mflux.models.common.config.model_config": {"AVAILABLE_MODELS": {"flux2-klein-4b": 1}},
            "mflux.models.common.resolution.config_resolution": {"ConfigResolution": Mock(resolve_restricted=Mock())},
            "mflux.models.flux2.variants": {"Flux2Klein": klein, "Flux2KleinEdit": klein_edit},
        }
    ):
        model = build_model("edit", "/weights/klein", None, StepHook())

    klein_edit.assert_called_once()
    klein.assert_not_called()
    assert model is klein_edit.return_value


def test_a_run_returns_the_image_the_model_made():
    recording = Recording()
    steps = []
    result = run(recording.models(), job(size="768x432", steps=3), steps)
    assert (result.width, result.height, result.seed, result.steps) == (768, 432, 5, 3)
    assert steps == [(0, 3)]
    assert recording.runs[0][1]["num_inference_steps"] == 3


def test_the_model_in_use_stays_warm_across_images_of_one_batch():
    # Building costs a load the page waits through, so a run that finishes keeps
    # its model. The second image is what an extra build would show up in.
    recording = Recording()
    models = recording.models()
    run(models, job(size="16x16"), [])
    run(models, job(size="16x16"), [])
    assert recording.builds == ["generate"]


def test_one_model_at_a_time():
    # Both variants load the same transformer, so a run in the other mode frees
    # the first. Keeping both resident runs the machine out of memory.
    recording = Recording()
    models = recording.models()
    run(models, job(size="16x16"), [])
    run(models, job("edit", references=(png(8, 8),), size="16x16"), [])
    run(models, job("edit", references=(png(8, 8),), size="16x16"), [])
    assert recording.builds == ["generate", "edit"]
    assert [mode for mode, _ in recording.runs] == ["generate", "edit", "edit"]


def test_release_drops_the_model_so_the_next_load_builds_again():
    recording = Recording()
    models = recording.models()
    models.load()
    models.release()
    models.load()
    assert recording.builds == ["generate", "generate"]


def test_release_hands_the_mlx_pool_back():
    # The pool holds 22.42 GB at 1024 between generations. A resident server is
    # the only thing that keeps it.
    clear_cache = Mock()
    models = KleinModels("dir", 8, build=Recording().build)
    with heavy_modules({"mlx.core": {"clear_cache": clear_cache}}):
        models.release()
    clear_cache.assert_called_once_with()


def test_the_pool_is_handed_back_after_every_run():
    clear_cache = Mock()
    models = KleinModels("dir", 8, build=Recording().build)
    models.load()  # built before the stub, so only the run's own release is counted
    with heavy_modules({"mlx.core": {"clear_cache": clear_cache}}):
        run(models, job(size="16x16"), [])
    clear_cache.assert_called_once_with()


def test_a_failure_on_the_engine_still_hands_the_pool_back():
    # A refused run is where the memory matters most: the page shows the error
    # and the user tries again, and the buffers of the failed run are not free.
    clear_cache = Mock()

    class Refusing(FakeModel):
        def generate_image(self, **kwargs):
            raise RuntimeError("out of memory")

    models = KleinModels("dir", 8, build=lambda mode, *_: Refusing(mode, []))
    models.load()
    with heavy_modules({"mlx.core": {"clear_cache": clear_cache}}), pytest.raises(RuntimeError, match="out of memory"):
        run(models, job(size="16x16"), [])
    clear_cache.assert_called_once_with()
