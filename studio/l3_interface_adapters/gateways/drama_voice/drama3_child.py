#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "mlx-audio @ git+https://github.com/Blaizzy/mlx-audio.git@2209e6d76c18d0a24f7ff64d35b4176258acd909",
#   "mlx==0.32.4", "mlx-metal==0.32.4 ; sys_platform == 'darwin'",
#   "numpy==2.5.4", "soundfile==0.14.0", "soxr==1.1.0",
#   "transformers==5.20.2", "huggingface-hub==2.2.0",
# ]
# ///
"""Resident Drama-3, with JSON pipes and native-rate streaming codec decoding."""

import base64
import contextlib
import importlib
import io
import json
import sys
from functools import partial

TEXT_CHUNK_BYTES = 180

WEIGHTS_REPO = "mlx-community/fish-audio-drama-3-8bit"
WEIGHTS_REVISION = "fedc7cc92bab5a180709cbaae6208d10b390bb97"


def log(message):
    print(message, file=sys.stderr, flush=True)


def load_engine():
    import mlx.core as mx
    from huggingface_hub import snapshot_download
    from mlx_audio.tts.utils import load_model

    mx.set_cache_limit(1024**3)
    weights = snapshot_download(WEIGHTS_REPO, revision=WEIGHTS_REVISION)
    from mlx_audio.tts.models.fish_drama3.chunking import split_text

    # The pinned engine binds this helper in its generation module. Smaller internal
    # chunks avoid long-script looping while the output remains one continuous clip.
    module = importlib.import_module("mlx_audio.tts.models.fish_drama3.drama3")
    module.split_text = partial(split_text, limit=TEXT_CHUNK_BYTES)
    return load_model(weights)


def reference_samples(encoded, sample_rate):
    import numpy as np
    import soundfile
    import soxr

    samples, rate = soundfile.read(io.BytesIO(base64.b64decode(encoded)), dtype="float32", always_2d=True)
    mono = samples.mean(axis=1)
    return np.asarray(soxr.resample(mono, rate, sample_rate) if rate != sample_rate else mono, dtype=np.float32)


def answer(engine, job):
    import mlx.core as mx
    import numpy as np
    import soundfile
    from mlx_audio.tts.models.fish_drama3.chunking import split_text

    mx.random.seed(job["seed"])
    mx.reset_peak_memory()
    options = {name: job[name] for name in ("max_tokens", "temperature", "top_k", "top_p") if name in job}
    limit = options.get("max_tokens", 1024)
    if job.get("audio"):
        options.update(ref_audio=reference_samples(job["audio"], engine.sample_rate), ref_text=job["ref_text"])
    chunks, tokens, per_segment, samples_per_segment = [], 0, {}, {}
    log("step 0/0")
    try:
        for result in engine.generate(text=job["text"], stream=True, streaming_interval=0.5, **options):
            count = per_segment.get(result.segment_idx, 0) + result.token_count
            per_segment[result.segment_idx] = count
            if count >= limit:
                raise ValueError(
                    "The audio reached max_tokens before completing. Increase max_tokens or shorten the script."
                )
            samples = np.array(result.audio, dtype=np.float32, copy=True)
            samples_per_segment[result.segment_idx] = samples_per_segment.get(result.segment_idx, 0) + len(samples)
            if len(samples):
                chunks.append(samples)
            tokens += result.token_count
            log(f"step {tokens}/0")
            mx.clear_cache()
        if not chunks:
            raise ValueError("Drama-3 returned no audio. Try another seed or a reference voice.")
        expected = set(range(len(split_text(job["text"], limit=TEXT_CHUNK_BYTES))))
        if set(per_segment) != expected or any(
            per_segment[index] == 0 or samples_per_segment[index] == 0 for index in expected
        ):
            raise ValueError(
                "Drama-3 did not produce audio for every script chunk. Try another seed or a reference voice."
            )
        audio = np.concatenate(chunks)
        if not np.isfinite(audio).all():
            raise RuntimeError("Drama-3 returned non-finite audio.")
        output = io.BytesIO()
        soundfile.write(output, audio, engine.sample_rate, format="WAV", subtype="PCM_16")
        log("step 1/1")
        return {
            "wav": base64.b64encode(output.getvalue()).decode("ascii"),
            "seconds": len(audio) / engine.sample_rate,
            "sample_rate": engine.sample_rate,
            "steps": tokens,
            "peak_memory_bytes": mx.get_peak_memory(),
        }
    finally:
        engine.codec.reset_streaming_state()
        mx.clear_cache()


def serve():
    with contextlib.redirect_stdout(sys.stderr):
        engine = load_engine()
    log("ready")
    for line in sys.stdin:
        try:
            job = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                response = answer(engine, job)
        except ValueError as error:
            response = {"error": str(error), "kind": "input"}
        except Exception as error:
            response = {"error": str(error)}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    serve()
