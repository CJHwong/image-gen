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
    groups = {}
    for command in selected:
        command.remove("--enhance-prompt")
        args = parser.parse_args(command[1:])
        if args.seed < 0:
            args.seed = random.randint(0, 2**31 - 1)
            if "--seed" in command:
                command[command.index("--seed") + 1] = str(args.seed)
            else:
                command.extend(("--seed", str(args.seed)))
        cli._guard_enhance_not_gemma4(args.gemma)
        image = args.images[0].path if args.images else None
        groups.setdefault((args.gemma, bool(image)), []).append((command, args, image))
    started = time.monotonic()
    index = 0
    for (checkpoint, conditioned), group in groups.items():
        model = (
            importlib.import_module("mlx_image_prompt_enhancement").ImagePromptEnhancer()
            if conditioned
            else encoder.GemmaLanguageModel()
        )
        try:
            model.load(checkpoint)
            for command, args, image in group:
                index += 1
                print(f"[Enhancing batch prompt {index}/{len(selected)}]", file=sys.stderr, flush=True)
                prompt = (
                    model.enhance_i2v(args.prompt, image, seed=args.seed)
                    if image
                    else model.enhance_t2v(args.prompt, seed=args.seed)
                )
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
