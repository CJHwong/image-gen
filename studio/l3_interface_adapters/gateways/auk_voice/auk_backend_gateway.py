# ruff: noqa: RUF001
"""AuK, run in its own child: clone, design and edit through one instruction call.

The child holds the engine and answers one call at a time: an instruction, at most
one clip, a length and a seed. This side decides what the calls are. It turns the
mode into AuK's instruction, splits a long text into calls that each fit, and joins
their clips.

`design` never returns what a design call says. Every design call opened with 1
to 2 seconds of junk, in 14 of 14 calls: the voice description read aloud, the
`<no_prompt_audio>` marker read aloud, or a later part of the text. So design
makes a short voice sample first and then clones every chunk from it, the first
included. A clone call opens clean, and every chunk keeps the one voice.

The sample says a fixed sentence, never the job's words. A clone of a sample with
the same words copied the sample, junk included, in 2 of 2 short texts. Design
reads a sentence of this length correctly: it scrambled only past 18 seconds.
"""

import base64
import io

import numpy as np
import soundfile

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.voice_job import SpeechJob, SpeechResult
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway
from studio.l3_interface_adapters.gateways.auk_voice.capabilities import auk_capabilities
from studio.l3_interface_adapters.gateways.auk_voice.chunks import HAN, chunk_text, estimate_seconds
from studio.l3_interface_adapters.gateways.voice_stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.voice_wav_audio import to_wav

GAP_SECONDS = 0.2  # the silence between two joined calls
SAMPLE_LINES = {  # what a design sample says, about 7 seconds each
    "zh": "今天天气很好，我们一起出去走走，顺便去市场买点水果和青菜，晚上再回家煮饭。",
    "en": "The morning was quiet and bright, so we walked along the river, stopped for coffee, and talked about the week ahead.",
}


def clone_instruction(text: str) -> str:
    return f'Say the following with the same voice: "{text}"'


def design_instruction(voice: str, text: str) -> str:
    if HAN.search(text):
        return f'请基于下面的描述: "{voice}",生成语音内容"{text}".'
    return f'Generate speech based on the following description: "{voice}". The content to speak is: "{text}".'


def _decode(wav: bytes) -> tuple[np.ndarray, int]:
    samples, rate = soundfile.read(io.BytesIO(wav), dtype="float32")
    return samples, rate


def _join(clips: list[bytes]) -> tuple[bytes, float, int]:
    decoded = [_decode(clip) for clip in clips]
    rate = decoded[0][1]
    gap = np.zeros(int(rate * GAP_SECONDS), dtype=np.float32)
    parts = [part for index, (samples, _) in enumerate(decoded) for part in ((gap, samples) if index else (samples,))]
    joined = np.concatenate(parts)
    return to_wav(joined, rate), len(joined) / rate, rate


class AukBackendGateway(VoiceBackendGateway):
    def __init__(self, child: StdioChild, variant: str):
        self._child = child
        self._capabilities = auk_capabilities(variant)
        self._voice_samples: dict[tuple[str, bool, bool], bytes] | None = None

    def capabilities(self):
        return self._capabilities

    def load(self) -> None:
        self._child.wait_ready()

    def release(self) -> None:
        self._voice_samples = None
        self._child.stop()

    def prepare_batch(self, jobs, should_stop) -> None:
        # A completed script can leak its words into a later clone. Reuse only the neutral sample.
        self._voice_samples = {}

    def run(self, job: SpeechJob, on_step, should_stop) -> SpeechResult:
        seconds = float(job.options.get("seconds", 0) or 0) or None
        if job.mode == "edit":
            convert = job.options.get("convert", "tw2s") == "tw2s"  # the words an edit puts in
            reply = self._call(job, job.text, job.references[0].wav, seconds, convert, on_step, should_stop)
            wav = base64.b64decode(reply["wav"])
            return SpeechResult(wav, reply["seconds"], reply["sample_rate"], job.seed, reply["steps"])
        return self._speak(job, seconds, on_step, should_stop)

    def _speak(self, job: SpeechJob, seconds: float | None, on_step, should_stop) -> SpeechResult:
        """clone and design: one clone call per chunk, in order, then one clip."""
        voice = str(job.options.get("voice", "")).strip()
        if job.mode == "design" and not voice:
            raise InvalidJob("Describe the voice to build under voice.")
        chunks = chunk_text(job.text)
        if seconds is not None and len(chunks) > 1:
            raise InvalidJob(
                f"seconds sets the length of one call, but this text needs {len(chunks)}. Set it to 0, or shorten the text."
            )
        convert = job.options.get("convert", "tw2s") == "tw2s"
        samples = self._voice_samples
        sample_key = (voice, convert, bool(HAN.search(job.text)))
        reference = samples.get(sample_key) if samples is not None else None
        if job.references:
            reference = job.references[0].wav
        calls = len(chunks) + int(reference is None)

        def call_step(call: int):
            """One progress bar over every call of the job."""
            return lambda step, total: on_step(call * total + step, calls * total)

        clips, steps = [], 0
        if reference is None:
            sample = self._voice_sample(job, voice, convert, call_step(0), should_stop)
            reference, steps = base64.b64decode(sample["wav"]), sample["steps"]
            if samples is not None:
                samples[sample_key] = reference
        first = calls - len(chunks)
        for index, chunk in enumerate(chunks):
            length = seconds or estimate_seconds(chunk)
            reply = self._call(
                job, clone_instruction(chunk), reference, length, convert, call_step(first + index), should_stop
            )
            clips.append(base64.b64decode(reply["wav"]))
            steps += reply["steps"]  # every call's steps, as the progress bar counted them
        wav, total_seconds, rate = _join(clips)
        return SpeechResult(wav, total_seconds, rate, job.seed, steps)

    def _voice_sample(self, job: SpeechJob, voice: str, convert: bool, on_step, should_stop) -> dict:
        """design: a short clip in the described voice, in the job's language. Never returned."""
        text = SAMPLE_LINES["zh" if HAN.search(job.text) else "en"]
        instruction = design_instruction(voice, text)
        return self._call(job, instruction, None, estimate_seconds(text), convert, on_step, should_stop)

    def _call(self, job, instruction, audio, seconds, convert, on_step, should_stop) -> dict:
        # The child only watches for a stop during a call. A stop that lands between two
        # calls is caught here, so the warm engine is not killed for it.
        if should_stop():
            raise Cancelled("stopped between two calls")
        payload = {
            "instruction": instruction,
            "audio": base64.b64encode(audio).decode("ascii") if audio is not None else None,
            "seconds": seconds,
            "seed": job.seed,
            "convert": convert,
        }
        return self._child.request(payload, on_step, should_stop)
