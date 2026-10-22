import importlib
from types import SimpleNamespace

import pytest
from PIL import Image

from studio.l4_frameworks_and_drivers.mlx_image_prompt_enhancement import ImagePromptEnhancer


@pytest.mark.parametrize("output", ["  A red shape moves.  ", "  "])
def test_vision_uses_pixels_native_instructions_seed_and_sampling(tmp_path, monkeypatch, output):
    calls = []
    picture = tmp_path / "reference.png"
    Image.new("RGBA", (32, 24), (255, 0, 0, 128)).save(picture)
    model, processor = SimpleNamespace(config=object()), object()

    def generate(*args, **options):
        assert args == (model, processor, "formatted")
        assert options.keys() == {"image", "max_tokens", "temperature", "verbose"}
        assert options["max_tokens"] == 512 and options["temperature"] == 0.7 and options["verbose"] is False
        image = options["image"][0]
        assert image.mode == "RGB" and image.size == (32, 24)
        assert image.getpixel((0, 0)) == (255, 0, 0)
        calls.append("generated")
        return SimpleNamespace(text=output)

    def template(selected_processor, config, messages, num_images):
        assert selected_processor is processor and config is model.config and num_images == 1
        assert messages == [
            {"role": "system", "content": "native instructions"},
            {"role": "user", "content": "User Raw Input Prompt: It moves."},
        ]
        return "formatted"

    modules = {
        "mlx_vlm": SimpleNamespace(load=lambda path: calls.append(path) or (model, processor), generate=generate),
        "mlx_vlm.prompt_utils": SimpleNamespace(apply_chat_template=template),
        "mlx.core": SimpleNamespace(random=SimpleNamespace(seed=lambda value: calls.append(("seed", value)))),
        "PIL.Image": Image,
        "ltx_core_mlx.text_encoders.gemma.encoders.base_encoder": SimpleNamespace(
            GemmaLanguageModel=lambda: SimpleNamespace(default_gemma_i2v_system_prompt="native instructions")
        ),
    }
    monkeypatch.setattr(importlib, "import_module", modules.__getitem__)
    enhancer = ImagePromptEnhancer()
    enhancer.load("same-gemma")
    if output.strip():
        assert enhancer.enhance_i2v("It moves", picture, seed=7) == output.strip()
    else:
        with pytest.raises(ValueError, match="empty prompt"):
            enhancer.enhance_i2v("It moves", picture, seed=7)
    assert calls == ["same-gemma", ("seed", 7), "generated"]


def test_missing_vision_dependency_names_the_engine_install(monkeypatch):
    def unavailable(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(importlib, "import_module", unavailable)
    with pytest.raises(RuntimeError, match=r"mlx-vlm==0\.4\.3"):
        ImagePromptEnhancer().load("gemma")
