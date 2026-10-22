"""Run native LTX prompt enhancement in its pinned engine environment."""

import hashlib
import json
import tempfile
from collections import OrderedDict
from pathlib import Path

from studio.l1_entities.errors import StudioError
from studio.l4_frameworks_and_drivers.mlx_video_runner import MlxVideoRunner


class MlxPromptEnhancer:
    def __init__(self, settings):
        self._cli = str(settings.get("cli_path", ""))
        self._runner = MlxVideoRunner(settings, "", True)
        self._enhanced = OrderedDict()

    def __call__(self, prompt, references, on_writing, should_stop):
        python = self._runner._checked(
            str(Path(self._cli).parent / "python"), "Set cli_path under [mlx_video] to the installed MLX engine."
        )
        with tempfile.TemporaryDirectory(prefix="studio-ltx-rewrite-") as scratch:
            root = Path(scratch)
            source, destination = root / "request.json", root / "result.json"
            image = None
            if references:
                image = root / "reference.png"
                image.write_bytes(references[0].png)
            source.write_text(json.dumps({"prompt": prompt, "image": str(image) if image else None}))
            child = Path(__file__).with_name("mlx_prompt_enhancement_child.py")
            tail = ""
            writing = False

            def consume(chunk):
                nonlocal tail, writing
                combined = tail + chunk
                tail = combined[-24:]
                if not writing and "[Studio enhancer writing]" in combined:
                    writing = True
                    on_writing()

            self._runner._execute(
                [python, str(child), str(source), str(destination)],
                None,
                should_stop,
                consume,
            )
            result = json.loads(destination.read_text())["prompt"]
            if not isinstance(result, str) or not result.strip():
                raise StudioError("The LTX enhancer returned an empty prompt. Try rewriting again.")
        self._enhanced[result, _reference_key(references)] = None
        while len(self._enhanced) > 128:
            self._enhanced.popitem(last=False)
        return result

    def is_enhanced(self, prompt, references):
        return (prompt, _reference_key(references)) in self._enhanced


def _reference_key(references):
    return hashlib.sha256(references[0].png).hexdigest() if references else None
