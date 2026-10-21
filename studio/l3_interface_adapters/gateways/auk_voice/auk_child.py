#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#     "auk @ git+https://github.com/Tencent-Hunyuan/AuK.git@6943a1e967409e8c73139a7a345f2a611cfb3dd6",
#     "mlx==0.32.2",
#     "mlx-metal==0.32.2 ; sys_platform == 'darwin'",
#     # upstream leaves transformers at >=4.52,<5 and validated the MLX port on 4.57
#     "transformers==4.57.6",
#     "huggingface-hub==0.35.3",
#     "numpy==2.2.6",
#     "soundfile==0.13.1",
#     "soxr==1.1.0",
#     # qwen-omni-utils imports audioread but declares only a bare librosa;
#     # librosa 1.0 dropped audioread, so a loose resolve fails on any audio input
#     "qwen-omni-utils==0.0.9",
#     "librosa==0.11.0",
#     "av==17.1.0",
#     "opencc-python-reimplemented==0.1.7",
# ]
# ///
"""The AuK engine, resident, answering one JSON call per line on stdin.

    {"instruction": "...", "audio": "<base64 WAV>" | null, "seconds": 12.5 | null,
     "seed": 7, "convert": true}
    -> {"wav": "<base64 WAV>", "seconds": 12.4, "sample_rate": 48000, "steps": 4}
    -> {"error": "..."}

Each DiT call prints `step n/N` on stderr, after `step 0/N` when a job starts.
`seconds` null takes the input's length. The processor reads a clip by path only,
so a clip lives in the server's scratch folder (SPEECH_GEN_SCRATCH) for one call.
stdout carries replies only: everything else the engine prints goes to stderr.

The weights are smcleod/AuK-MLX-8bit at a fixed revision. It is bit-identical to a
conversion from the official checkpoint, and it saves a 57 GB download of it.

USAGE:
    uv run auk_child.py --variant flash
"""

import argparse
import base64
import functools
import hashlib
import io
import json
import os
import sys
from pathlib import Path

WEIGHTS_REPO = "smcleod/AuK-MLX-8bit"
WEIGHTS_REVISION = "abffd38adf7d9f0a94822e7c153e0c4ef70ef213"
BITS = 8
BASE_STEPS = 32  # the upstream default; flash fixes its own 4


def log(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def load_engine(variant: str):
    from auk_mlx.infer import AukMLX
    from huggingface_hub import snapshot_download

    log(f"fetching {WEIGHTS_REPO} ({variant}, {BITS}-bit)")
    weights = Path(
        snapshot_download(
            WEIGHTS_REPO,
            revision=WEIGHTS_REVISION,
            allow_patterns=[
                f"dit_{variant}.q{BITS}.safetensors",
                f"fusion_{variant}.safetensors",
                f"config_{variant}.yaml",
                "vae.safetensors",
                "thinker/*",
                "qwen/*",
            ],
        )
    )
    log("loading")
    engine = AukMLX(
        str(weights), str(weights / f"config_{variant}.yaml"), str(weights / "qwen"), bits=BITS, sequential=False
    )
    engine.dit = CountedDit(engine.dit, 4 if variant == "flash" else BASE_STEPS)
    reference_cache = ReferenceCache(engine)
    engine.load_audio = reference_cache.load_audio
    engine.encode_audio = reference_cache.encode_audio
    engine.encode_text = ConditioningCache(engine).encode_text
    return engine


class ReferenceCache:
    """Keep one reference in the child; release it when another reference arrives."""

    def __init__(self, engine):
        self._load_audio = engine.load_audio
        self._encode_audio = engine.encode_audio
        self._sample_rate = engine.sample_rate
        self._fingerprint = None
        self._audio = None
        self._latent = None

    def load_audio(self, path):
        fingerprint = (hashlib.sha256(Path(path).read_bytes()).digest(), self._sample_rate)
        if fingerprint == self._fingerprint:
            return self._audio
        self._fingerprint = self._audio = self._latent = None
        audio = self._load_audio(path)
        self._fingerprint, self._audio = fingerprint, audio
        return audio

    def encode_audio(self, audio):
        import mlx.core as mx

        if audio is not self._audio:
            return self._encode_audio(audio)
        if self._latent is None:
            latent = self._encode_audio(audio)
            mx.eval(latent)
            self._latent = latent
        return self._latent


class ConditioningCache:
    """Keep only the last instruction and reference conditioning for retakes."""

    def __init__(self, engine):
        self._encode_text = engine.encode_text
        self._key = None
        self._embedding = None

    def encode_text(self, messages):
        import mlx.core as mx

        references = tuple(
            hashlib.sha256(Path(part["audio"]).read_bytes()).digest()
            for message in messages
            for part in message.get("content", [])
            if part.get("type") == "audio"
        )
        key = (json.dumps(messages, sort_keys=True), references)
        if key == self._key:
            return self._embedding
        self._key = self._embedding = None
        embedding = self._encode_text(messages)
        mx.eval(embedding)
        self._key, self._embedding = key, embedding
        return embedding


class CountedDit:
    """The DiT, printing a step line per call. The sampler calls it once per step.

    MLX is lazy: a call returns before any work is done. So the wrapper evaluates
    the result first, or every step line would print at once, before the work.
    """

    def __init__(self, dit, total: int):
        self._dit = dit
        self.total = total
        self.done = 0

    def __call__(self, *args, **kwargs):
        import mlx.core as mx

        out = self._dit(*args, **kwargs)
        mx.eval(out)
        self.done += 1
        log(f"step {self.done}/{self.total}")
        return out

    def __getattr__(self, name):
        return getattr(self._dit, name)


@functools.cache
def tw2s():
    """Built once: opencc reads its dictionaries on every build, 14.5 s of a 40 s clone."""
    import opencc

    return opencc.OpenCC("tw2s")


def to_simplified(text: str) -> str:
    """AuK misreads Traditional Chinese. tw2s changes characters, not vocabulary."""
    return tw2s().convert(text)


def answer(engine, job: dict) -> dict:
    import mlx.core as mx
    import numpy as np
    import soundfile
    from auk_mlx.infer import GenerateOptions

    instruction = to_simplified(job["instruction"]) if job.get("convert") else job["instruction"]
    options = GenerateOptions(gen_seconds=job.get("seconds"), seed=job.get("seed"), nfe=BASE_STEPS)
    engine.dit.done = 0
    log(f"step 0/{engine.dit.total}")
    path = None
    if job.get("audio"):
        path = Path(os.environ["SPEECH_GEN_SCRATCH"]) / "in.wav"
        path.write_bytes(base64.b64decode(job["audio"]))
    try:
        audio, rate = engine.generate(instruction, audio_path=str(path) if path else None, opts=options)
    finally:
        if path is not None:
            path.unlink(missing_ok=True)
        # MLX keeps freed buffers for reuse up to its memory limit, 25 GB on a 32 GB Mac.
        # Kept between jobs, they grew the child from 6 GB of weights to 24 GB in three.
        mx.clear_cache()
    samples = np.asarray(audio, dtype=np.float32)
    buffer = io.BytesIO()
    soundfile.write(buffer, samples, rate, format="WAV", subtype="PCM_16")
    return {
        "wav": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "seconds": len(samples) / rate,
        "sample_rate": rate,
        "steps": engine.dit.done,
    }


def serve(variant: str) -> None:
    """One JSON line in, one out. json.dumps escapes newlines, so a message is one line."""
    replies, sys.stdout = sys.stdout, sys.stderr  # an engine library may print on stdout
    engine = load_engine(variant)
    log("ready")
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        try:
            reply = answer(engine, json.loads(line))
        except Exception as error:  # the server shows it; the engine stays up for the next call
            reply = {"error": f"{type(error).__name__}: {error}"}
        print(json.dumps(reply), file=replies, flush=True)


def main():
    parser = argparse.ArgumentParser(description="The AuK engine child. Speaks JSON lines on stdin and stdout.")
    parser.add_argument("--variant", choices=["flash", "base"], default="flash")
    serve(parser.parse_args().variant)


if __name__ == "__main__":
    main()
