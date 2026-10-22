"""Expose the same Gemma strategies used by the LTX CLI without rendering video."""

import importlib
import json
import sys
from pathlib import Path


def main():
    source, destination = map(Path, sys.argv[1:])
    request = json.loads(source.read_text())
    cli = importlib.import_module("ltx_pipelines_mlx.cli")
    encoder = importlib.import_module("ltx_core_mlx.text_encoders.gemma.encoders.base_encoder")
    cleanup = importlib.import_module("ltx_core_mlx.utils.memory").aggressive_cleanup
    image = request["image"]
    model = (
        importlib.import_module("mlx_image_prompt_enhancement").ImagePromptEnhancer()
        if image
        else encoder.GemmaLanguageModel()
    )
    try:
        model.load(cli.DEFAULT_GEMMA)
        print("[Studio enhancer writing]", file=sys.stderr, flush=True)
        prompt = (
            model.enhance_i2v(request["prompt"], image, seed=10)
            if image
            else model.enhance_t2v(request["prompt"], seed=10)
        )
        destination.write_text(json.dumps({"prompt": prompt}))
    finally:
        del model
        cleanup()


if __name__ == "__main__":
    main()
