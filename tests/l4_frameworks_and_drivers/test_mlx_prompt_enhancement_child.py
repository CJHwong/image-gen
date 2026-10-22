import json
import runpy
from types import SimpleNamespace

import pytest

from studio.l4_frameworks_and_drivers import mlx_prompt_enhancement_child as child


@pytest.mark.parametrize("entrypoint", [False, True])
@pytest.mark.parametrize("conditioned", [False, True])
@pytest.mark.parametrize("fails", [False, True])
def test_child_uses_native_strategy_and_always_frees_model(
    tmp_path, monkeypatch, capsys, conditioned, fails, entrypoint
):
    calls = []

    def enhanced(prompt, *images, seed):
        calls.append((prompt, images, seed))
        if fails:
            raise RuntimeError("Engine failed")
        return "A directed shot."

    model = SimpleNamespace(load=lambda name: calls.append(name), enhance_t2v=enhanced, enhance_i2v=enhanced)
    modules = {
        "mlx_image_prompt_enhancement": SimpleNamespace(ImagePromptEnhancer=lambda: model),
        "ltx_pipelines_mlx.cli": SimpleNamespace(DEFAULT_GEMMA="native-gemma"),
        "ltx_core_mlx.text_encoders.gemma.encoders.base_encoder": SimpleNamespace(GemmaLanguageModel=lambda: model),
        "ltx_core_mlx.utils.memory": SimpleNamespace(aggressive_cleanup=lambda: calls.append("freed")),
    }

    # Distinct functions prove the selected native strategy.
    def other(*_args, **_kwargs):
        pytest.fail("Wrong enhancement strategy")

    if conditioned:
        model.enhance_t2v = other
    else:
        model.enhance_i2v = other
    source, destination = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text(json.dumps({"prompt": "A cup", "image": "ref.png" if conditioned else None}))
    monkeypatch.setattr(child.sys, "argv", ["child", str(source), str(destination)])
    monkeypatch.setattr(child.importlib, "import_module", modules.__getitem__)
    if fails:
        with pytest.raises(RuntimeError):
            runpy.run_path(child.__file__, run_name="__main__") if entrypoint else child.main()
        assert not destination.exists()
    else:
        runpy.run_path(child.__file__, run_name="__main__") if entrypoint else child.main()
        assert json.loads(destination.read_text()) == {"prompt": "A directed shot."}
    assert calls == ["native-gemma", ("A cup", ("ref.png",) if conditioned else (), 10), "freed"]
    assert "[Studio enhancer writing]" in capsys.readouterr().err
