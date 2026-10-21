"""Enhance the batch before any video pipeline or prompt encoder is loaded."""

import importlib
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, cast


def enhance_commands(commands):
    selected = [command for command in commands if "--enhance-prompt" in command]
    if not selected:
        return
    cli = cast(Any, importlib.import_module("ltx_pipelines_mlx.cli"))
    encoder = cast(Any, importlib.import_module("ltx_core_mlx.text_encoders.gemma.encoders.base_encoder"))
    cleanup = cast(Any, importlib.import_module("ltx_core_mlx.utils.memory")).aggressive_cleanup
    parser = cli._build_parser()
    model = encoder.GemmaLanguageModel()
    started = time.monotonic()
    try:
        for index, command in enumerate(selected, 1):
            command.remove("--enhance-prompt")
            args = parser.parse_args(command[1:])
            if args.seed < 0:
                args.seed = random.randint(0, 2**31 - 1)
                if "--seed" in command:
                    command[command.index("--seed") + 1] = str(args.seed)
                else:
                    command.extend(("--seed", str(args.seed)))
            cli._guard_enhance_not_gemma4(args.gemma)
            if index == 1:
                model.load(args.gemma)
            print(f"[Enhancing batch prompt {index}/{len(selected)}]", file=sys.stderr, flush=True)
            # Match the native CLI's enhancement strategy and per-item seed exactly.
            if getattr(args, "image", None):
                prompt = model.enhance_i2v(args.prompt, seed=args.seed)
            else:
                prompt = model.enhance_t2v(args.prompt, seed=args.seed)
            command[command.index("-p") + 1] = prompt
    finally:
        del model
        cleanup()
    print(f"[Batch prompt enhancement: {time.monotonic() - started:.3f}s]", file=sys.stderr, flush=True)


def main():
    manifest = Path(sys.argv[1])
    commands = json.loads(manifest.read_text())
    enhance_commands(commands)
    manifest.write_text(json.dumps(commands))


if __name__ == "__main__":
    main()
