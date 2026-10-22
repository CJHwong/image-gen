"""The AuK child, driven in-process with AuK, MLX, the hub and opencc stubbed.

The stubs record what the child asks of the engine, so each test checks the
contract: the weights it fetches, the options it passes, and the JSON it answers.
"""

import base64
import importlib.util
import io
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import Mock

import numpy as np
import pytest

from tests.support import SOURCE_ROOT
from tests.support.heavy import heavy_modules
from tests.support.voice_audio import read, wav

CHILD_SCRIPT = SOURCE_ROOT / "l3_interface_adapters/gateways/audio/auk_runtime/auk_child.py"
RATE = 48000


def load_child():
    spec = importlib.util.spec_from_file_location("auk_child_under_test", CHILD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeAuk:
    """The engine. generate() calls the DiT as the sampler would, and records its arguments."""

    built: ClassVar[list] = []

    def __init__(self, mlx_dir, config_path, qwen_dir, bits, sequential):
        FakeAuk.built.append((mlx_dir, config_path, qwen_dir, bits, sequential))
        self.dit = Mock(return_value="velocity")
        self.calls = []
        self.fail = None
        self.sample_rate = RATE
        self.load_audio = Mock()
        self.encode_audio = Mock()
        self.encode_text = Mock()

    def generate(self, instruction, audio_path=None, opts=None):
        if self.fail:
            raise self.fail
        heard = Path(audio_path).read_bytes() if audio_path else None
        self.calls.append((instruction, audio_path, heard, opts))
        for _ in range(4):
            self.dit(x=1)
        return np.full(RATE // 2, 0.1, dtype=np.float32), RATE


class FakeConverter:
    built = 0

    def __init__(self, config):
        assert config == "tw2s"
        FakeConverter.built += 1

    def convert(self, text):
        return text.replace("颱風", "台风")


@pytest.fixture
def engines(tmp_path):
    FakeAuk.built = []
    download = Mock(return_value=str(tmp_path))
    evaluate = Mock()
    free = Mock()
    options = Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
    stubs = {
        "auk_mlx.infer": {"AukMLX": FakeAuk, "GenerateOptions": options},
        "huggingface_hub": {"snapshot_download": download},
        "mlx.core": {"eval": evaluate, "clear_cache": free},
        "opencc": {"OpenCC": FakeConverter},
    }
    with heavy_modules(stubs):
        yield SimpleNamespace(download=download, evaluate=evaluate, free=free, weights=tmp_path)


def drive(monkeypatch, child, lines, variant="flash"):
    """Feed the child's loop the given lines, and return its answers and its stderr."""
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(
        sys, "stdin", SimpleNamespace(buffer=io.BytesIO("".join(f"{line}\n" for line in lines).encode()))
    )
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    child.serve(variant)
    return [json.loads(line) for line in stdout.getvalue().splitlines()], stderr.getvalue()


def job(**overrides):
    return json.dumps(
        {"instruction": "Say hi.", "audio": None, "seconds": 2.0, "seed": 7, "convert": False, **overrides}
    )


def test_the_variant_fetches_only_its_own_weights_at_the_pinned_revision(engines):
    child = load_child()
    engine = child.load_engine("base")
    kwargs = engines.download.call_args.kwargs
    assert engines.download.call_args.args == ("smcleod/AuK-MLX-8bit",)
    assert kwargs["revision"] == child.WEIGHTS_REVISION
    assert (
        "dit_base.q8.safetensors" in kwargs["allow_patterns"]
        and "dit_flash.q8.safetensors" not in kwargs["allow_patterns"]
    )
    weights = engines.weights
    assert FakeAuk.built == [(str(weights), str(weights / "config_base.yaml"), str(weights / "qwen"), 8, False)]
    assert engine.dit.total == 32


def test_a_call_answers_a_wav_and_the_steps_the_dit_ran(engines, monkeypatch):
    answers, said = drive(monkeypatch, load_child(), [job()])
    (answer,) = answers
    samples, rate = read(base64.b64decode(answer["wav"]))
    assert (rate, len(samples), answer["seconds"], answer["sample_rate"], answer["steps"]) == (
        RATE,
        RATE // 2,
        0.5,
        RATE,
        4,
    )
    assert "step 1/4" in said and "step 4/4" in said and said.index("ready") < said.index("step 1/4")
    assert said.index("step 0/4") < said.index("step 1/4")  # the bar starts when the job does
    assert engines.evaluate.call_count == 4  # each step is evaluated before it is reported


def test_the_step_count_starts_again_for_every_call(engines, monkeypatch):
    answers, _ = drive(monkeypatch, load_child(), [job(), job()])
    assert [answer["steps"] for answer in answers] == [4, 4]


def test_a_clip_reaches_the_engine_as_a_file_in_the_scratch_folder_gone_after_the_call(engines, monkeypatch, tmp_path):
    monkeypatch.setenv("SPEECH_GEN_SCRATCH", str(tmp_path))
    child = load_child()
    engine = child.load_engine("flash")
    clip = wav(0.2)
    child.answer(engine, json.loads(job(audio=base64.b64encode(clip).decode())))
    _, path, heard, _ = engine.calls[0]
    assert heard == clip and Path(path).parent == tmp_path and not Path(path).exists()


def test_a_clip_is_gone_even_when_the_engine_fails(engines, monkeypatch, tmp_path):
    monkeypatch.setenv("SPEECH_GEN_SCRATCH", str(tmp_path))
    child = load_child()
    engine = child.load_engine("flash")
    engine.generate = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("too long"))
    with pytest.raises(ValueError):
        child.answer(engine, json.loads(job(audio=base64.b64encode(wav(0.2)).decode())))
    assert list(tmp_path.iterdir()) == []


def test_every_call_hands_the_freed_buffers_back_even_when_the_engine_fails(engines):
    # MLX caches freed buffers up to its memory limit: kept, they grew the real child to 24 GB.
    child = load_child()
    engine = child.load_engine("flash")
    child.answer(engine, json.loads(job()))
    child.answer(engine, json.loads(job()))
    engine.fail = ValueError("too long")
    with pytest.raises(ValueError):
        child.answer(engine, json.loads(job()))
    assert engines.free.call_count == 3


def test_the_options_carry_the_length_the_seed_and_the_base_steps(engines):
    child = load_child()
    engine = child.load_engine("flash")
    child.answer(engine, json.loads(job(seconds=None)))
    instruction, path, _, options = engine.calls[0]
    assert (instruction, path) == ("Say hi.", None)
    assert (options.gen_seconds, options.seed, options.nfe) == (None, 7, 32)


def test_convert_turns_traditional_into_simplified_first(engines):
    child = load_child()
    engine = child.load_engine("flash")
    child.answer(engine, json.loads(job(instruction="颱風假", convert=True)))
    assert engine.calls[0][0] == "台风假"


def test_the_converter_is_built_once_for_every_call(engines):
    # opencc reads its dictionaries on each build, 14.5 s of a 40 s clone in the real run.
    child = load_child()
    engine = child.load_engine("flash")
    FakeConverter.built = 0
    for _ in range(3):
        child.answer(engine, json.loads(job(instruction="颱風假", convert=True)))
    assert FakeConverter.built == 1
    assert [call[0] for call in engine.calls] == ["台风假"] * 3


def test_an_engine_error_is_answered_and_the_loop_goes_on(engines, monkeypatch):
    child = load_child()
    engine = child.load_engine("flash")
    engine.fail = ValueError("reference audio must be given as audio_path")
    monkeypatch.setattr(child, "load_engine", lambda variant: engine)
    answers, _ = drive(monkeypatch, child, [job(), "", "not json"])
    assert answers == [
        {"error": "ValueError: reference audio must be given as audio_path"},
        {"error": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"},
    ]


def test_the_dit_wrapper_passes_every_other_attribute_through(engines):
    child = load_child()
    dit = Mock()
    counted = child.CountedDit(dit, 4)
    counted.clear_cache()
    assert dit.clear_cache.call_count == 1


def test_main_reads_the_variant(engines, monkeypatch):
    child = load_child()
    serve = Mock()
    monkeypatch.setattr(child, "serve", serve)
    monkeypatch.setattr(sys, "argv", ["auk_child.py", "--variant", "base"])
    child.main()
    assert serve.call_args.args == ("base",)


def test_the_script_serves_as_main_until_stdin_closes(engines, monkeypatch):
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "argv", [str(CHILD_SCRIPT)])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"")))
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    runpy.run_path(str(CHILD_SCRIPT), run_name="__main__")
    assert stdout.getvalue() == "" and FakeAuk.built[0][1].endswith("config_flash.yaml")


def test_what_the_engine_prints_goes_to_stderr_not_into_the_replies(engines, monkeypatch):
    child = load_child()
    real_load = child.load_engine

    def noisy_load(variant):
        print("Loading weights 100%")  # as mlx-audio does, on stdout
        return real_load(variant)

    monkeypatch.setattr(child, "load_engine", noisy_load)
    answers, said = drive(monkeypatch, child, [job()])  # every stdout line must parse as a reply
    assert len(answers) == 1 and "Loading weights 100%" in said


@pytest.fixture
def reference_cache(engines, tmp_path):
    loader = Mock(side_effect=lambda path: bytearray(Path(path).read_bytes()))
    encoder = Mock(side_effect=lambda audio: bytes(audio))
    engine = SimpleNamespace(load_audio=loader, encode_audio=encoder, sample_rate=24000)
    cache = load_child().ReferenceCache(engine)
    path = tmp_path / "in.wav"
    path.write_bytes(b"first")
    return SimpleNamespace(cache=cache, path=path, loader=loader, encoder=encoder, evaluate=engines.evaluate)


def test_reference_cache_reuses_only_a_materialized_latent(reference_cache):
    prepared = reference_cache
    audio = prepared.cache.load_audio(prepared.path)
    assert prepared.cache.encode_audio(audio) == b"first"
    prepared.evaluate.assert_called_once_with(b"first")
    assert prepared.cache.encode_audio(prepared.cache.load_audio(prepared.path)) == b"first"
    assert prepared.loader.call_count == prepared.encoder.call_count == prepared.evaluate.call_count == 1


def test_reference_cache_evicts_old_content_even_when_the_path_stays_the_same(reference_cache):
    prepared = reference_cache
    prepared.cache.encode_audio(prepared.cache.load_audio(prepared.path))
    prepared.path.write_bytes(b"second")
    assert prepared.cache.encode_audio(prepared.cache.load_audio(prepared.path)) == b"second"
    prepared.path.write_bytes(b"first")
    assert prepared.cache.encode_audio(prepared.cache.load_audio(prepared.path)) == b"first"
    assert prepared.loader.call_count == prepared.encoder.call_count == 3


def test_reference_cache_keys_content_instead_of_the_file_name(reference_cache):
    prepared = reference_cache
    audio = prepared.cache.load_audio(prepared.path)
    other = prepared.path.with_name("other.wav")
    other.write_bytes(prepared.path.read_bytes())
    assert prepared.cache.load_audio(other) is audio
    prepared.loader.assert_called_once()


def test_reference_cache_passes_external_audio_to_the_original_encoder(reference_cache):
    prepared = reference_cache
    prepared.cache.encode_audio(prepared.cache.load_audio(prepared.path))
    assert prepared.cache.encode_audio(bytearray(b"external")) == b"external"
    assert prepared.encoder.call_count == 2


def test_reference_cache_retries_after_latent_evaluation_fails(reference_cache):
    prepared = reference_cache
    audio = prepared.cache.load_audio(prepared.path)
    prepared.evaluate.side_effect = [RuntimeError("evaluation failed"), None]
    with pytest.raises(RuntimeError, match="evaluation failed"):
        prepared.cache.encode_audio(audio)
    assert prepared.cache.encode_audio(audio) == b"first"
    assert prepared.encoder.call_count == 2


def test_reference_cache_does_not_keep_old_audio_when_new_decoding_fails(reference_cache):
    prepared = reference_cache
    prepared.cache.encode_audio(prepared.cache.load_audio(prepared.path))
    prepared.path.write_bytes(b"second")
    prepared.loader.side_effect = RuntimeError("bad audio")
    with pytest.raises(RuntimeError, match="bad audio"):
        prepared.cache.load_audio(prepared.path)
    prepared.loader.side_effect = lambda path: bytearray(Path(path).read_bytes())
    assert prepared.cache.encode_audio(prepared.cache.load_audio(prepared.path)) == b"second"


def test_each_engine_owns_its_reference_cache(engines):
    first = load_child().load_engine("flash")
    second = load_child().load_engine("flash")
    assert first.load_audio.__self__ is first.encode_audio.__self__
    assert first.load_audio.__self__ is not second.load_audio.__self__
    assert first.encode_text.__self__ is not second.encode_text.__self__


@pytest.fixture
def conditioning_cache(engines, tmp_path):
    encoder = Mock(side_effect=lambda messages: json.dumps(messages, sort_keys=True).encode())
    cache = load_child().ConditioningCache(SimpleNamespace(encode_text=encoder))
    path = tmp_path / "reference.wav"
    path.write_bytes(b"reference one")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Say this line."},
                {"type": "audio", "audio": str(path)},
            ],
        }
    ]
    return SimpleNamespace(cache=cache, encoder=encoder, messages=messages, path=path, evaluate=engines.evaluate)


def test_conditioning_cache_reuses_the_exact_instruction_and_reference(conditioning_cache):
    prepared = conditioning_cache
    first = prepared.cache.encode_text(prepared.messages)
    assert prepared.cache.encode_text(prepared.messages) is first
    assert prepared.encoder.call_count == prepared.evaluate.call_count == 1


def test_conditioning_cache_keeps_only_the_last_instruction(conditioning_cache):
    prepared = conditioning_cache
    prepared.cache.encode_text(prepared.messages)
    other = [{"role": "user", "content": [{"type": "text", "text": "Another instruction."}]}]
    prepared.cache.encode_text(other)
    prepared.cache.encode_text(prepared.messages)
    assert prepared.encoder.call_count == 3


def test_conditioning_cache_reads_reference_content_even_when_its_path_stays_the_same(conditioning_cache):
    prepared = conditioning_cache
    prepared.cache.encode_text(prepared.messages)
    prepared.path.write_bytes(b"reference two")
    prepared.cache.encode_text(prepared.messages)
    assert prepared.encoder.call_count == 2


def test_conditioning_cache_reuses_text_without_an_audio_reference(conditioning_cache):
    prepared = conditioning_cache
    messages = [{"role": "user", "content": [{"type": "text", "text": "Design this voice."}]}]
    first = prepared.cache.encode_text(messages)
    assert prepared.cache.encode_text(messages) is first
    prepared.encoder.assert_called_once()


def test_conditioning_cache_drops_failed_evaluations(conditioning_cache):
    prepared = conditioning_cache
    prepared.evaluate.side_effect = [RuntimeError("evaluation failed"), None]
    with pytest.raises(RuntimeError, match="evaluation failed"):
        prepared.cache.encode_text(prepared.messages)
    prepared.cache.encode_text(prepared.messages)
    assert prepared.encoder.call_count == 2
