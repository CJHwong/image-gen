import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l4_frameworks_and_drivers.mlx_prompt_enhancer import MlxPromptEnhancer


def enhancer(tmp_path):
    python = tmp_path / "python"
    python.touch()
    return MlxPromptEnhancer({"cli_path": str(tmp_path / "ltx-2-mlx")})


@pytest.mark.parametrize("conditioned", [False, True])
def test_native_enhancement_uses_engine_environment_and_tracks_exact_output(tmp_path, monkeypatch, conditioned):
    engine = enhancer(tmp_path)
    writing = []
    references = (SimpleNamespace(png=b"image-a"),) if conditioned else ()

    def execute(command, progress, stop, consume):
        assert command[0] == str(tmp_path / "python")
        assert Path(command[1]).name == "mlx_prompt_enhancement_child.py"
        request = json.loads(Path(command[2]).read_text())
        assert request["prompt"] == "A cup"
        if conditioned:
            assert Path(request["image"]).read_bytes() == b"image-a"
        else:
            assert request["image"] is None
        assert progress is None and stop() is False
        consume("Loading weights\n[Studio enhan")
        consume("cer writing]\n" + "Writing tokens\n" * 100)
        assert writing == [True]
        consume("[Studio enhancer writing]\n")
        Path(command[3]).write_text(json.dumps({"prompt": "A directed shot."}))

    monkeypatch.setattr(engine._runner, "_execute", execute)
    assert engine("A cup", references, lambda: writing.append(True), lambda: False) == "A directed shot."
    assert writing == [True]
    assert engine.is_enhanced("A directed shot.", references)
    assert not engine.is_enhanced("A directed shot. Edited.", references)
    assert not engine.is_enhanced("A directed shot.", () if conditioned else (SimpleNamespace(png=b"other"),))


@pytest.mark.parametrize("output", ["", None])
def test_empty_enhancement_is_not_cached(tmp_path, monkeypatch, output):
    engine = enhancer(tmp_path)
    monkeypatch.setattr(
        engine._runner, "_execute", lambda command, *_: Path(command[3]).write_text(json.dumps({"prompt": output}))
    )
    with pytest.raises(StudioError, match="empty prompt"):
        engine("A cup", (), lambda: None, lambda: False)
    assert not engine._enhanced


def test_enhancement_cancellation_does_not_cache_output(tmp_path, monkeypatch):
    engine = enhancer(tmp_path)

    def execute(*_):
        raise Cancelled("Stopped")

    monkeypatch.setattr(engine._runner, "_execute", execute)
    with pytest.raises(Cancelled):
        engine("A cup", (), lambda: None, lambda: True)
    assert not engine._enhanced


def test_enhancement_history_is_bounded(tmp_path, monkeypatch):
    engine = enhancer(tmp_path)
    count = iter(range(129))
    monkeypatch.setattr(
        engine._runner,
        "_execute",
        lambda command, *_: Path(command[3]).write_text(json.dumps({"prompt": str(next(count))})),
    )
    for _ in range(129):
        engine("A cup", (), lambda: None, lambda: False)
    assert len(engine._enhanced) == 128
    assert not engine.is_enhanced("0", ()) and engine.is_enhanced("128", ())


def test_enhanced_image_cache_matches_pixels_instead_of_reference_presence(tmp_path, monkeypatch):
    engine = enhancer(tmp_path)
    monkeypatch.setattr(
        engine._runner, "_execute", lambda command, *_: Path(command[3]).write_text(json.dumps({"prompt": "A shot."}))
    )
    first, changed = SimpleNamespace(png=b"first"), SimpleNamespace(png=b"changed")
    engine("A cup", (first,), lambda: None, lambda: False)
    assert engine.is_enhanced("A shot.", (first,))
    assert engine.is_enhanced("A shot.", (SimpleNamespace(png=b"first"), changed))
    assert not engine.is_enhanced("A shot.", (changed,))
    assert not engine.is_enhanced("A shot.", ())
