"""Apply the engine's native enhancer to audio-conditioned Generate too.

The pinned CLI exposes --enhance-prompt for generate, but not a2v. Its same helper
can run before the audio pipeline without loading either video pack alongside it.
"""

import importlib
import sys
from pathlib import Path
from typing import Any, cast


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gemma3"))
    cli = cast(Any, importlib.import_module("ltx_pipelines_mlx.cli"))
    original = cli._cmd_a2v
    native_enhance = cli._maybe_enhance_prompt

    def enhance(args):
        images = getattr(args, "images", None)
        if not getattr(args, "enhance_prompt", False) or not images:
            return native_enhance(args)
        cli._guard_enhance_not_gemma4(args.gemma)
        helper = importlib.import_module("mlx_image_prompt_enhancement")
        cleanup = importlib.import_module("ltx_core_mlx.utils.memory").aggressive_cleanup
        model = helper.ImagePromptEnhancer()
        try:
            model.load(args.gemma)
            return model.enhance_i2v(args.prompt, images[0].path, seed=args.seed)
        finally:
            del model
            cleanup()

    cli._maybe_enhance_prompt = enhance

    def enhanced_audio(args):
        args.enhance_prompt = True
        args.prompt = cli._maybe_enhance_prompt(args)
        return original(args)

    cli._cmd_a2v = enhanced_audio
    cli.main()


if __name__ == "__main__":
    main()
