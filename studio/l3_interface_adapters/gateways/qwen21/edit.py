"""Qwen-Image-2.1 instruction editing, through the diffusers child qwen21_edit.py next to this file.

Editing cannot live in this process. It needs diffusers and torch, and this
server runs on MLX; the two pull different, heavy dependency trees, and mflux
has never ported the Qwen3-VL vision tower that instruction editing needs.

The child stays up between edits, because building the pipeline costs 20 to 36
seconds: two 768 edits measured 31.9s then 19.6s down one child.
"""

import base64

from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.png_images import to_pil
from studio.l3_interface_adapters.gateways.qwen21.capabilities import EDIT_MATCH_CAP, MATCH
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild


def edit_payload(job: ImageJob) -> dict:
    options = job.options
    if options["resolution"] == MATCH:
        # The pipeline sizes from the last reference, so match that one. A marked
        # edit appends the mask last, and maskDataUrl writes the mask at the
        # reference's own pixel size, so the picture and the mask agree and the
        # output follows the picture either way.
        last = job.references[-1]
        resolution = min(round((last.width * last.height) ** 0.5), EDIT_MATCH_CAP)
    else:
        resolution = int(str(options["resolution"]))
    return {
        "prompt": job.prompt,
        "images": [base64.b64encode(reference.png).decode("ascii") for reference in job.references],
        "negative_prompt": options["negative"] or None,
        "true_cfg_scale": options["cfg"],
        "steps": options["steps"],
        "output_resolution": resolution,
        "seed": job.seed,
    }


class Qwen21Edit:
    def __init__(self, child: StdioChild):
        self._child = child

    def load(self) -> None:
        self._child.ensure()

    def release(self) -> None:
        self._child.stop()

    def run(self, job: ImageJob, on_step, should_stop) -> ImageResult:
        reply = self._child.request(edit_payload(job), on_step, should_stop)
        png = base64.b64decode(reply["image"])
        image = to_pil(png)
        return ImageResult(
            png=png, width=image.width, height=image.height, seed=reply["seed"], steps=int(job.options["steps"])
        )
