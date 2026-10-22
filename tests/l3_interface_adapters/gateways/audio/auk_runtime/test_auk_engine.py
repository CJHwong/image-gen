import base64

import numpy as np
import pytest

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.voice_job import ReferenceAudio, SpeechJob
from studio.l3_interface_adapters.gateways.audio.auk_runtime.auk_engine import (
    GAP_SECONDS,
    SAMPLE_LINES,
    AukEngine,
    clone_instruction,
    design_instruction,
)
from studio.l3_interface_adapters.gateways.audio.auk_runtime.chunks import MIN_SECONDS
from studio.l3_interface_adapters.gateways.audio.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.audio.wav_audio import to_wav
from tests.support.voice_audio import read

RATE = 48000
LONG = " ".join([" ".join(["word"] * 20) + "."] * 6)  # two chunks
VOICE_WAV = to_wav(np.zeros(RATE // 10, dtype=np.float32), RATE)
CLIP = ReferenceAudio(wav=VOICE_WAV, seconds=0.1, sample_rate=RATE)


class FakeChild(StdioChild):
    """Answers each call with a clip of `seconds` (default one), and records the payloads.

    It starts no process: every method the gateway calls is replaced.
    """

    def __init__(self, steps=4):
        super().__init__([])
        self.payloads = []
        self.events = []
        self.steps = steps

    def wait_ready(self):
        self.events.append("wait_ready")

    def stop(self):
        self.events.append("stop")

    def request(self, payload, on_step, should_stop):
        self.payloads.append(payload)
        for step in range(1, self.steps + 1):
            on_step(step, self.steps)
        seconds = payload["seconds"] or 1.0
        wav = to_wav(np.full(int(seconds * RATE), 0.1, dtype=np.float32), RATE)
        return {"wav": base64.b64encode(wav).decode(), "seconds": seconds, "sample_rate": RATE, "steps": self.steps}


def gateway(child=None):
    return AukEngine(child or FakeChild(), "flash")


def run(backend, job):
    steps = []
    result = backend.run(job, lambda step, total: steps.append((step, total)), lambda: False)
    return result, steps


def test_load_starts_the_child_and_release_stops_it():
    child = FakeChild()
    backend = gateway(child)
    backend.load()
    backend.release()
    assert child.events == ["wait_ready", "stop"] and backend.capabilities().backend_id == "auk"


def test_a_clone_sends_the_clip_and_the_instruction():
    child = FakeChild()
    result, _ = run(gateway(child), SpeechJob("clone", "Hello there.", 7, {"seconds": 0, "convert": "tw2s"}, (CLIP,)))
    (payload,) = child.payloads
    assert payload["instruction"] == 'Say the following with the same voice: "Hello there."'
    assert base64.b64decode(payload["audio"]) == VOICE_WAV
    assert (payload["seed"], payload["convert"]) == (7, True)
    assert payload["seconds"] == pytest.approx(MIN_SECONDS)  # two words, below the shortest window
    assert (result.sample_rate, result.seed, result.steps) == (RATE, 7, 4)


def test_an_asked_length_goes_to_the_engine_as_it_is():
    child = FakeChild()
    result, _ = run(gateway(child), SpeechJob("clone", "Hi.", 7, {"seconds": 2.5, "convert": "off"}, (CLIP,)))
    assert (child.payloads[0]["seconds"], child.payloads[0]["convert"]) == (2.5, False)
    assert result.seconds == pytest.approx(2.5)


def test_a_long_text_is_one_call_per_chunk_joined_with_a_gap():
    child = FakeChild()
    result, _ = run(gateway(child), SpeechJob("clone", LONG, 7, {"seconds": 0}, (CLIP,)))
    assert len(child.payloads) == 2
    assert all(base64.b64decode(p["audio"]) == VOICE_WAV for p in child.payloads)
    expected = sum(p["seconds"] for p in child.payloads) + GAP_SECONDS
    samples, _ = read(result.wav)
    assert result.seconds == pytest.approx(expected, abs=1e-3) and len(samples) / RATE == pytest.approx(
        expected, abs=1e-3
    )


def test_the_steps_of_every_chunk_fill_one_progress_bar():
    _, steps = run(gateway(), SpeechJob("clone", LONG, 7, {"seconds": 0}, (CLIP,)))
    assert steps == [(1, 8), (2, 8), (3, 8), (4, 8), (5, 8), (6, 8), (7, 8), (8, 8)]


def test_a_chinese_design_samples_the_voice_in_chinese():
    child = FakeChild()
    run(gateway(child), SpeechJob("design", "大家好。", 7, {"voice": "溫柔女聲", "seconds": 0}))
    assert f'"{SAMPLE_LINES["zh"]}"' in child.payloads[0]["instruction"]


def test_design_clones_every_chunk_from_a_short_voice_sample():
    child = FakeChild()
    result, steps = run(gateway(child), SpeechJob("design", LONG, 7, {"voice": " a calm narrator ", "seconds": 0}))
    sample, *clones = child.payloads
    assert sample["audio"] is None and sample["instruction"].startswith(
        'Generate speech based on the following description: "a calm narrator"'
    )
    assert f'"{SAMPLE_LINES["en"]}"' in sample["instruction"]  # never the job's own words
    assert len(clones) == 2 and all(
        c["instruction"].startswith("Say the following with the same voice") for c in clones
    )
    assert all(c["audio"] == base64.b64encode(read_back(sample)).decode() for c in clones)
    # the sample is the voice only: the clip is the clones, joined
    assert result.seconds == pytest.approx(sum(c["seconds"] for c in clones) + GAP_SECONDS, abs=1e-3)
    assert steps[0] == (1, 12) and steps[-1] == (12, 12)


def read_back(payload):
    """The clip the fake child made for this payload, as the gateway received it."""
    return to_wav(np.full(int(payload["seconds"] * RATE), 0.1, dtype=np.float32), RATE)


def test_design_without_a_voice_is_refused_before_the_engine_runs():
    child = FakeChild()
    with pytest.raises(InvalidJob, match="Describe the voice"):
        run(gateway(child), SpeechJob("design", "Hello.", 7, {"voice": "  "}))
    assert child.payloads == []


def test_a_fixed_length_over_many_chunks_is_refused():
    child = FakeChild()
    with pytest.raises(InvalidJob, match="this text needs 2"):
        run(gateway(child), SpeechJob("clone", LONG, 7, {"seconds": 10}, (CLIP,)))
    assert child.payloads == []


def test_an_edit_is_one_call_with_the_instruction_as_written():
    child = FakeChild()
    result, steps = run(
        gateway(child), SpeechJob("edit", "Raise the pitch by 2 semitones.", 7, {"seconds": 0}, (CLIP,))
    )
    (payload,) = child.payloads
    assert (payload["instruction"], payload["seconds"], payload["convert"]) == (
        "Raise the pitch by 2 semitones.",
        None,
        True,  # the words an edit puts in are Chinese too, and AuK misreads Traditional
    )
    assert steps[-1] == (4, 4) and result.seconds == 1.0


def test_an_edit_can_keep_its_words_as_written():
    child = FakeChild()
    run(gateway(child), SpeechJob("edit", "Replace 'a' with '颱風假'.", 7, {"seconds": 0, "convert": "off"}, (CLIP,)))
    assert child.payloads[0]["convert"] is False


def test_a_design_reports_the_steps_of_every_call_it_made():
    result, steps = run(gateway(), SpeechJob("design", LONG, 7, {"voice": "calm", "seconds": 0}))
    assert result.steps == 12 == steps[-1][1]  # the sample and two chunks, 4 steps each


def test_a_stop_between_two_calls_ends_the_job_without_another_call():
    child = FakeChild()
    stops = iter([False, True])
    with pytest.raises(Cancelled, match="between two calls"):
        gateway(child).run(SpeechJob("clone", LONG, 7, {"seconds": 0}, (CLIP,)), lambda s, t: None, lambda: next(stops))
    assert len(child.payloads) == 1


def test_the_instructions_follow_the_cookbook_wording():
    assert clone_instruction("hi") == 'Say the following with the same voice: "hi"'
    assert design_instruction("溫柔女聲", "你好") == '请基于下面的描述: "溫柔女聲",生成语音内容"你好".'
    assert design_instruction("calm", "hi") == (
        'Generate speech based on the following description: "calm". The content to speak is: "hi".'
    )


def test_batch_reuses_a_neutral_sample_instead_of_the_completed_script():
    child = FakeChild()
    backend = gateway(child)
    jobs = [
        SpeechJob("design", text, seed, {"voice": "calm", "seconds": 2.5})
        for text, seed in [("Bring the red teapot.", 7), ("Bring the green bowl.", 8)]
    ]
    backend.prepare_batch(jobs, lambda: False)
    first, first_steps = run(backend, jobs[0])
    second, second_steps = run(backend, jobs[1])
    sample, first_clone, second_clone = child.payloads
    assert SAMPLE_LINES["en"] in sample["instruction"]
    neutral = base64.b64encode(read_back(sample)).decode()
    assert first_clone["audio"] == second_clone["audio"] == neutral
    assert base64.b64decode(second_clone["audio"]) != first.wav
    assert second_clone["instruction"] == clone_instruction(jobs[1].text)
    assert first_steps[0] == (1, 8) and first_steps[-1] == (8, 8)
    assert second_steps == [(1, 4), (2, 4), (3, 4), (4, 4)]
    assert first.steps == 8 and second.steps == 4


def test_batch_voice_samples_keep_language_voice_and_conversion_separate():
    child = FakeChild()
    backend = gateway(child)
    jobs = [
        SpeechJob("design", "Hello.", 7, {"voice": "calm", "seconds": 2.5}),
        SpeechJob("design", "你好。", 8, {"voice": "calm", "seconds": 2.5}),
        SpeechJob("design", "Hello again.", 9, {"voice": "deep", "seconds": 2.5}),
        SpeechJob("design", "Hello once more.", 10, {"voice": "calm", "seconds": 2.5, "convert": "off"}),
    ]
    backend.prepare_batch(jobs, lambda: False)
    for entry in [*jobs, *jobs]:
        run(backend, entry)
    samples = [payload for payload in child.payloads if payload["audio"] is None]
    assert len(samples) == 4
    assert SAMPLE_LINES["en"] in samples[0]["instruction"]
    assert SAMPLE_LINES["zh"] in samples[1]["instruction"]
    assert '"deep"' in samples[2]["instruction"]
    assert samples[3]["convert"] is False
    assert len(child.payloads) == 12


def test_another_batch_does_not_reuse_a_previous_batches_voice_sample():
    child = FakeChild()
    backend = gateway(child)
    entry = SpeechJob("design", "Hello.", 7, {"voice": "calm", "seconds": 2.5})
    for seed in (7, 8):
        backend.prepare_batch([entry], lambda: False)
        run(backend, SpeechJob(entry.mode, entry.text, seed, entry.options))
    samples = [payload for payload in child.payloads if payload["audio"] is None]
    assert [payload["seed"] for payload in samples] == [7, 8]


def test_single_runs_without_batch_preparation_keep_independent_voice_samples():
    child = FakeChild()
    backend = gateway(child)
    entry = SpeechJob("design", "Hello.", 7, {"voice": "calm", "seconds": 2.5})
    run(backend, entry)
    run(backend, entry)
    assert len(child.payloads) == 4


def test_explicit_clone_reference_takes_precedence_over_a_cached_design_sample():
    child = FakeChild()
    backend = gateway(child)
    design = SpeechJob("design", "Bring the red teapot.", 7, {"voice": "calm", "seconds": 2.5})
    clone = SpeechJob("clone", "Bring the green bowl.", 8, design.options, references=(CLIP,))
    backend.prepare_batch([design, clone], lambda: False)
    run(backend, design)
    run(backend, clone)
    assert len(child.payloads) == 3
    assert child.payloads[-1]["audio"] == base64.b64encode(CLIP.wav).decode()
    assert child.payloads[-1]["instruction"] == clone_instruction(clone.text)


def test_release_discards_the_batch_voice_before_a_later_direct_run():
    child = FakeChild()
    backend = gateway(child)
    entry = SpeechJob("design", "Hello.", 7, {"voice": "calm", "seconds": 2.5})
    backend.prepare_batch([entry], lambda: False)
    run(backend, entry)
    backend.release()
    backend.load()
    run(backend, entry)
    assert len(child.payloads) == 4
    assert child.events == ["stop", "wait_ready"]
