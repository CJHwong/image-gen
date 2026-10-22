from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.support.heavy import heavy_modules


@pytest.mark.parametrize("fail", [False, True])
def test_restore_loads_only_the_encoder_and_restores_bits(fail, monkeypatch):
    from studio.l3_interface_adapters.gateways.image.qwen_runtime.encoder_restore import restore_text_encoder

    encoder = object()
    components = [
        SimpleNamespace(name="transformer"),
        SimpleNamespace(name="text_encoder"),
        SimpleNamespace(name="vae"),
    ]
    definition = type("Definition", (), {"get_components": staticmethod(lambda: components)})
    model = SimpleNamespace(bits=8, text_encoder=None, transformer=object(), vae=object(), prompt_cache={"pear": ()})
    preserved = model.transformer, model.vae, model.prompt_cache

    def load(target, root, weights, quantize, *, validate):
        assert target is model and root == Path("/weights") and quantize == 8 and validate
        assert [component.name for component in weights.get_components()] == ["text_encoder"]
        assert target.text_encoder is encoder
        target.bits = 4
        if fail:
            raise ValueError("bad encoder weights")

    modules = {
        "mflux.models.qwen21.qwen21_initializer": {"Qwen21Initializer": SimpleNamespace(load_components=load)},
        "mflux.models.qwen21.weights.qwen21_weight_definition": {"Qwen21WeightDefinition": definition},
        "mflux.models.qwen21.model.qwen21_text_encoder.qwen21_text_encoder": {"Qwen21TextEncoder": lambda: encoder},
    }
    freed = Mock()
    monkeypatch.setattr(
        "studio.l3_interface_adapters.gateways.image.qwen_runtime.encoder_restore.release_mlx_buffers", freed
    )
    with heavy_modules(modules):
        if fail:
            with pytest.raises(ValueError, match="bad encoder weights"):
                restore_text_encoder(model, model_path="/weights", quantize=8)
        else:
            restore_text_encoder(model, model_path="/weights", quantize=8)
    assert model.bits == 8
    assert (model.transformer, model.vae, model.prompt_cache) == preserved
    assert model.text_encoder is (None if fail else encoder)
    assert freed.call_count == int(fail)
