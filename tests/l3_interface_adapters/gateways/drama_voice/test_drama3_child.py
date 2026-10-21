"""Drive the child without importing or loading MLX weights."""

import base64
import importlib.util
import io
import json
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from tests.support import SOURCE_ROOT
from tests.support.heavy import heavy_modules
from tests.support.voice_audio import read, wav_b64

SCRIPT = SOURCE_ROOT / "l3_interface_adapters/gateways/drama_voice/drama3_child.py"


def load_child():
    spec = importlib.util.spec_from_file_location("drama_child_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def result(samples, tokens=2, segment=0):
    return SimpleNamespace(audio=np.asarray(samples, dtype=np.float32), token_count=tokens, segment_idx=segment)


@pytest.fixture
def engine():
    engine = Mock(sample_rate=44100)
    engine.generate.return_value = [result([0.1, 0.2]), result([], tokens=0), result([0.3, 0.4])]
    return engine


@pytest.fixture
def runtime(engine, tmp_path):
    seed, clear, limit = Mock(), Mock(), Mock()
    load, download = Mock(return_value=engine), Mock(return_value=tmp_path)
    resample = Mock(side_effect=lambda samples, old, new: np.repeat(samples, 2))
    split = Mock(side_effect=lambda text, limit: text.split("|"))
    generation_module = SimpleNamespace(split_text=None)
    stubs = {
        "mlx.core": {
            "random": SimpleNamespace(seed=seed),
            "reset_peak_memory": Mock(),
            "clear_cache": clear,
            "set_cache_limit": limit,
            "get_peak_memory": lambda: 123,
        },
        "mlx_audio.tts.utils": {"load_model": load},
        "mlx_audio.tts.models.fish_drama3.chunking": {"split_text": split},
        "mlx_audio.tts.models.fish_drama3.drama3": generation_module.__dict__,
        "huggingface_hub": {"snapshot_download": download},
        "soxr": {"resample": resample},
    }
    with heavy_modules(stubs):
        yield SimpleNamespace(
            seed=seed, clear=clear, limit=limit, load=load, download=download, resample=resample, split=split
        )


def test_load_uses_pinned_weights_and_a_bounded_allocator(runtime, engine):
    child = load_child()
    assert child.load_engine() is engine
    runtime.download.assert_called_once_with(child.WEIGHTS_REPO, revision=child.WEIGHTS_REVISION)
    runtime.load.assert_called_once_with(runtime.download.return_value)
    runtime.limit.assert_called_once_with(1024**3)
    import importlib

    splitter = importlib.import_module("mlx_audio.tts.models.fish_drama3.drama3").split_text
    assert splitter("First|Second") == ["First", "Second"]
    runtime.split.assert_called_once_with("First|Second", limit=180)


@pytest.mark.parametrize("rate,resamples", [(44100, False), (22050, True)])
def test_api_reference_is_mono_and_resampled_to_native_rate(runtime, rate, resamples):
    samples = load_child().reference_samples(wav_b64(0.5, rate, 2), 44100)
    assert samples.ndim == 1 and samples.dtype == np.float32
    assert runtime.resample.called == resamples
    if resamples:
        assert runtime.resample.call_args.args[1:] == (22050, 44100)
    assert len(samples) == 22050


@pytest.mark.parametrize("reference", [False, True])
def test_streaming_joins_all_chunks_at_native_rate_and_keeps_sampling(runtime, engine, reference, capsys):
    child = load_child()
    job = {"text": "[whispers] Hello", "seed": 7, "temperature": 0.7, "top_p": 0.7, "top_k": 30, "max_tokens": 1024}
    if reference:
        job.update(audio=wav_b64(rate=44100), ref_text="The reference words.")
    answer = child.answer(engine, job)
    samples, rate = read(base64.b64decode(answer["wav"]))
    assert rate == 44100 and len(samples) == 4 and np.allclose(samples, [0.1, 0.2, 0.3, 0.4], atol=0.0001)
    runtime.split.assert_called_once_with(job["text"], limit=180)
    assert answer["steps"] == 4 and answer["peak_memory_bytes"] == 123
    assert answer["seconds"] == 4 / 44100
    runtime.seed.assert_called_once_with(7)
    options = engine.generate.call_args.kwargs
    assert options["text"] == "[whispers] Hello" and options["stream"] and options["streaming_interval"] == 0.5
    assert options["max_tokens"] == 1024 and options["top_k"] == 30
    assert ("ref_audio" in options) == reference
    if reference:
        assert options["ref_text"] == "The reference words." and options["ref_audio"].ndim == 1
    engine.codec.reset_streaming_state.assert_called_once_with()
    lines = capsys.readouterr().err
    assert "step 0/0" in lines and "step 4/0" in lines and "step 1/1" in lines
    assert runtime.clear.call_count == 4


@pytest.mark.parametrize("kind", ["empty", "cap", "default_cap", "nonfinite", "engine"])
def test_failed_generation_does_not_publish_a_partial_clip_and_resets_codec(runtime, engine, kind):
    job = {"text": "Hello", "seed": 7}
    error = ValueError
    if kind == "empty":
        engine.generate.return_value = []
    elif kind in ("cap", "default_cap"):
        engine.generate.return_value = [result([0.1], tokens=1024 if kind == "cap" else 2048)]
        if kind == "cap":
            job["max_tokens"] = 1024
    elif kind == "nonfinite":
        engine.generate.return_value = [result([np.nan])]
        error = RuntimeError
    else:
        engine.generate.side_effect = RuntimeError("engine failure")
        error = RuntimeError
    with pytest.raises(error) as caught:
        load_child().answer(engine, job)
    if kind == "default_cap":
        assert "Shorten the script" in str(caught.value)
        assert "up to 2048" in str(caught.value)
    engine.codec.reset_streaming_state.assert_called_once_with()
    assert runtime.clear.called


def test_resident_loop_isolates_errors_and_keeps_stdout_json(monkeypatch, runtime, engine, capsys):
    child = load_child()
    monkeypatch.setattr(child, "load_engine", lambda: engine)
    monkeypatch.setattr(
        child, "answer", Mock(side_effect=[ValueError("bad job"), RuntimeError("engine failed"), {"wav": "ok"}])
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}\n{}\n{}\n"))
    child.serve()
    output = capsys.readouterr()
    assert [json.loads(line) for line in output.out.splitlines()] == [
        {"error": "bad job", "kind": "input"},
        {"error": "engine failed"},
        {"wav": "ok"},
    ]
    assert "ready" in output.err


def test_script_entry_point_handles_invalid_json_and_serves_empty_input(monkeypatch, runtime, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json\n"))
    runpy.run_path(str(SCRIPT), run_name="__main__")
    output = capsys.readouterr()
    assert json.loads(output.out)["kind"] == "input" and "ready" in output.err


@pytest.mark.parametrize("final", ["missing", "empty", "tokens_without_audio"])
def test_every_internal_text_chunk_must_produce_audio(runtime, engine, final):
    outputs = [result([0.1, 0.2])]
    if final != "missing":
        outputs.append(result([], tokens=0 if final == "empty" else 2, segment=1))
    engine.generate.return_value = outputs
    with pytest.raises(ValueError, match="every script chunk"):
        load_child().answer(engine, {"text": "First chunk|Second chunk", "seed": 7})
    engine.codec.reset_streaming_state.assert_called_once_with()


def test_multiple_productive_internal_chunks_form_one_continuous_clip(runtime, engine):
    engine.generate.return_value = [result([0.1, 0.2]), result([0.3], segment=1), result([], tokens=0, segment=1)]
    answer = load_child().answer(engine, {"text": "First chunk|Second chunk", "seed": 7})
    assert len(read(base64.b64decode(answer["wav"]))[0]) == 3


def test_omitted_token_limit_forwards_2048_and_allows_output_past_old_default(runtime, engine):
    engine.generate.return_value = [result([0.1], tokens=1500)]
    answer = load_child().answer(engine, {"text": "Hello", "seed": 7})
    assert answer["steps"] == 1500
    assert engine.generate.call_args.kwargs["max_tokens"] == 2048
