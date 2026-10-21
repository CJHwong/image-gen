import gc
import weakref
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from tests.support.heavy import heavy_modules


def test_evaluated_cache_enforces_memory_and_entry_bounds():
    from studio.l3_interface_adapters.gateways.qwen21.edit_input_cache import EvaluatedCache

    evaluated = Mock()
    with heavy_modules({"mlx.core": {"eval": evaluated}}):
        cache = EvaluatedCache(max_entries=2, max_bytes=16)
        first, second, third = [np.zeros(2, dtype=np.float32) for _ in range(3)]
        assert cache.get("first", lambda: first) is first
        assert cache.get("second", lambda: second) is second
        assert cache.get("first", Mock(side_effect=AssertionError)) is first
        assert cache.get("third", lambda: third) is third
        assert list(cache.entries) == ["first", "third"]
        assert cache.bytes == 16
        too_large = Mock(return_value=np.zeros(5, dtype=np.float32))
        cache.get("large", too_large)
        cache.get("large", too_large)
        assert too_large.call_count == 2 and cache.bytes == 16
        cache = EvaluatedCache(max_entries=8, max_bytes=8)
        cache.get("tuple", lambda: (first,))
        cache.get("second", lambda: second)
        assert list(cache.entries) == ["second"]


@pytest.mark.parametrize("evaluation_fails", [False, True])
def test_failed_encoding_clears_cached_arrays(evaluation_fails):
    from studio.l3_interface_adapters.gateways.qwen21.edit_input_cache import EvaluatedCache

    evaluated = Mock()
    with heavy_modules({"mlx.core": {"eval": evaluated}}):
        cache = EvaluatedCache()
        cache.get("first", lambda: np.zeros(2))
        load = Mock(return_value=np.zeros(2))
        if evaluation_fails:
            evaluated.side_effect = ValueError("failed encode")
        else:
            load.side_effect = ValueError("failed encode")
        with pytest.raises(ValueError, match="failed encode"):
            cache.get("failed", load)
        assert not cache.entries and cache.bytes == 0


def test_installed_cache_uses_actual_ordered_images_and_numeric_inputs():
    from studio.l3_interface_adapters.gateways.qwen21.edit_input_cache import cache_edit_inputs

    encoded = (np.zeros(2), np.ones(2))
    prompt = Mock(return_value=encoded)
    vae = Mock(side_effect=lambda pixels: pixels)
    model = SimpleNamespace(_encode_prompt=prompt, vae=SimpleNamespace(encode=vae))
    blue, red = Image.new("RGB", (2, 2), "blue"), Image.new("RGB", (2, 2), "red")
    with heavy_modules({"mlx.core": {"eval": Mock()}}):
        cache_edit_inputs(model)
        for images in [
            [blue],
            [blue.copy()],
            [red],
            [blue.resize((4, 4))],
            [blue.convert("RGBA")],
            [blue, red],
            [red, blue],
        ]:
            assert model._encode_prompt("paint", images) is encoded
        model._encode_prompt("change", [blue])
        assert prompt.call_count == 7
        pixels = np.zeros((1, 2), dtype=np.float32)
        assert model.vae.encode(pixels) is pixels
        assert model.vae.encode(pixels.copy()) is pixels
        model.vae.encode(pixels.astype(np.float64))
        model.vae.encode(pixels.reshape(2, 1))
        model.vae.encode(np.ones_like(pixels))
        assert vae.call_count == 4


def test_model_release_collects_cached_arrays_and_bound_wrappers():
    from studio.l3_interface_adapters.gateways.qwen21.edit_input_cache import cache_edit_inputs

    class Model:
        def __init__(self):
            self.vae = SimpleNamespace(encode=lambda pixels: pixels)

        def _encode_prompt(self, prompt, images):
            return (np.zeros(2), np.ones(2))

    model = Model()
    with heavy_modules({"mlx.core": {"eval": lambda *arrays: None}}):
        cache_edit_inputs(model)
        encoded = model._encode_prompt("paint", [])
        model_reference, array_reference = weakref.ref(model), weakref.ref(encoded[0])
        del encoded, model
        gc.collect()
        assert model_reference() is None and array_reference() is None
