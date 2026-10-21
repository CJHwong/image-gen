"""Apply the engine's native enhancer to audio-conditioned Generate too.

The pinned CLI exposes --enhance-prompt for generate, but not a2v. Its same helper
can run before the audio pipeline without loading either video pack alongside it.
"""

import importlib
from typing import Any, cast


def main():
    cli = cast(Any, importlib.import_module("ltx_pipelines_mlx.cli"))
    original = cli._cmd_a2v

    def enhanced_audio(args):
        args.enhance_prompt = True
        args.prompt = cli._maybe_enhance_prompt(args)
        return original(args)

    cli._cmd_a2v = enhanced_audio
    cli.main()


if __name__ == "__main__":
    main()
