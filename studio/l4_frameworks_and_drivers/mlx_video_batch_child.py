"""Run inside the MLX environment, which does not install the studio package."""

import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any, cast


def retain_pipeline(commands, policy="resident"):
    distilled = cast(Any, importlib.import_module("ltx_pipelines_mlx.distilled"))
    mx = importlib.import_module("mlx.core")

    if policy != "resident":
        mx.set_cache_limit(1024**3)
    original = distilled.DistilledPipeline
    retained = []

    def factory(*arguments, **options):
        if retained:
            return retained[0]
        options["low_memory"] = policy == "offload"
        pipeline = original(*arguments, **options)
        embeddings = {}
        started = time.monotonic()
        for command in commands:
            prompt = command[command.index("-p") + 1]
            if prompt in embeddings:
                continue
            embeddings[prompt] = pipeline.prompt_encoder.encode(prompt)
            mx.eval(*embeddings[prompt])
        pipeline.prompt_encoder.free()
        pipeline._load_text_encoder = lambda: None
        pipeline._encode_text = embeddings.__getitem__
        if policy != "resident":
            aggressive_cleanup = cast(Any, importlib.import_module("ltx_core_mlx.utils.memory")).aggressive_cleanup

            def wrap(method):
                def invoke(*arguments, **options):
                    result = method(*arguments, **options)
                    aggressive_cleanup()
                    return result

                return invoke

            for name in ("_stage1", "_upsample_latent", "_stage2", "_decode_and_save_video"):
                setattr(pipeline, name, wrap(getattr(pipeline, name)))
        retained.append(pipeline)
        print(f"[Batch prompt encoding: {time.monotonic() - started:.3f}s]", file=sys.stderr, flush=True)
        return pipeline

    distilled.DistilledPipeline = factory


def execute(manifest: Path, policy="resident"):
    commands = json.loads(manifest.read_text())
    if policy != "sequential":
        retain_pipeline(commands, policy)
    main = importlib.import_module("ltx_pipelines_mlx.cli").main

    for index, command in enumerate(commands, 1):
        emit("start", index)
        sys.argv = command
        main()
        if policy == "sequential":
            cast(Any, importlib.import_module("ltx_core_mlx.utils.memory")).aggressive_cleanup()
        emit("done", index)
        acknowledgement = manifest.parent / f"{index}.ack"
        while not acknowledgement.exists():
            time.sleep(0.05)


def emit(event: str, index: int):
    print("\nSTUDIO_BATCH:" + json.dumps({"event": event, "index": index}), file=sys.stderr, flush=True)


if __name__ == "__main__":
    execute(Path(sys.argv[-1]), sys.argv[1] if len(sys.argv) > 2 else "resident")
