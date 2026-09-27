"""The Qwen-Image-2.1 prompt rewriters, through mlx-vlm in this process.

One model per mode. PE-T2I lengthens a request for generate, PE-I2I reads the
picture the run will carry and lengthens an edit instruction. Both are
fine-tuned Qwen3.5-VL 9B, 18.84 GB in bf16, and both answer in JSON after an
optional thinking block.

They run on MLX, the same engine the generate half uses, so unlike the edit
engine they need no child process. The child exists because torch and MLX cannot
share one process, and mlx-vlm does not pull torch. Its import is deferred to the
first rewrite and costs 1.6s, so a studio that never rewrites never pays it.

The two models do not both fit beside anything, so this adapter keeps at most one
resident and drops it when the other mode asks.
"""

import io
import json
from collections.abc import Mapping
from typing import cast

from PIL import Image

from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l3_interface_adapters.gateways.mflux_runtime import release_mlx_buffers

# The card's own sampling settings, and its token budget. Measured 2026-09-27:
# 317 to 505 tokens out in 22 to 32s, so the budget is never reached.
MAX_TOKENS = 16384


def _system_prompt(repo: str) -> str:
    """The instructions shipped beside the weights. The model depends on them."""
    from huggingface_hub import hf_hub_download

    with open(hf_hub_download(repo, "system_prompt.txt"), encoding="utf-8") as handle:
        return handle.read().strip()


def _as_rewrite(text: str) -> PromptRewrite:
    """The JSON the card says follows the thinking block.

    A model that answers in prose has still written a longer prompt, so the text
    is used as it stands rather than failing the click. Measured 2026-09-27: no
    thinking block is emitted at all, so the whole answer is already the JSON.
    """
    _, marker, tail = text.rpartition("</think>")
    body = (tail if marker else text).strip()
    if body.startswith("```"):
        body = body.split("```")[1].removeprefix("json").strip()
    try:
        answer = json.loads(body)
    except json.JSONDecodeError:
        return PromptRewrite(prompt=body)
    return PromptRewrite(
        prompt=answer.get("rewritten_prompt") or body,
        ratio=answer.get("wh_ratio") or None,
        follow_reference=bool(answer.get("ratio_follow")),
    )


class Qwen21Rewriter(PromptRewriterGateway):
    def __init__(self, models: Mapping[str, str]):
        self._models = dict(models)
        self._resident: tuple | None = None

    def modes(self) -> tuple[str, ...]:
        return tuple(self._models)

    def rewrite(self, prompt: str, mode: str, references: tuple[ReferenceImage, ...]) -> PromptRewrite:
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        model, processor, config, system_prompt = self._resident_for(mode)
        # A PIL image, not a path: the studio tells its user it writes nothing to
        # disk, and mlx-vlm's load_image takes an Image.Image as it takes a path.
        images = [Image.open(io.BytesIO(reference.png)).convert("RGB") for reference in references]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        # apply_chat_template returns a message list only when return_messages is
        # set, and its hint cannot say so, so the string form is taken here.
        formatted = cast(str, apply_chat_template(processor, config, messages, num_images=len(images)))
        result = generate(
            model,
            processor,
            formatted,
            # mlx-vlm's hint for this parameter says str or list[str], and its own
            # process_image only calls load_image for a str: a PIL image is passed
            # straight through. Verified against the installed source, 2026-09-27.
            image=images or None,  # ty: ignore[invalid-argument-type]
            max_tokens=MAX_TOKENS,
            temperature=1.0,
            top_p=0.95,
            top_k=20,
            enable_thinking=True,
            verbose=False,
        )
        return _as_rewrite(result.text)

    def release(self) -> None:
        if self._resident is None:
            return
        self._resident = None
        release_mlx_buffers()

    def _resident_for(self, mode: str) -> tuple:
        if self._resident is not None and self._resident[0] == mode:
            return self._resident[1:]
        self.release()
        from huggingface_hub import logging as hub_logging
        from huggingface_hub.utils import disable_progress_bars
        from mlx_vlm import load
        from mlx_vlm.utils import load_config

        # Resolving a cached model still makes huggingface_hub print a line and a
        # progress bar, and this server keeps its terminal quiet. Both of these
        # are runtime switches, so they work whatever imported it first.
        disable_progress_bars()
        hub_logging.set_verbosity_error()
        repo = self._models[mode]
        model, processor = load(repo)
        self._resident = (mode, model, processor, load_config(repo), _system_prompt(repo))
        return self._resident[1:]
