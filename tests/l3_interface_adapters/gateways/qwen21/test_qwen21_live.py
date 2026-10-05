"""The real qwen21 weights: one generate, one edit, one cancel.

Nothing here is mocked. The unit tests beside this file stub every engine call, so
a break inside mflux reads exactly like a break this repo caused. This is the test
that tells the two apart, which `PORTABILITY.md` listed as the repo's first gap: it
had none, and flux2 was its only live test.

The edit half is the one that matters. Until this change the edit ran on a diffusers
pipeline in a child process; it now runs on the same MLX engine as generate, and the
swap is only proven by real pixels coming out of the new path.
"""

from pathlib import Path

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.qwen21.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.qwen21.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.qwen21.qwen21_backend_gateway import Qwen21BackendGateway
from tests.support.images import png

# The hub snapshot the studio downloads on first use. A machine without it skips
# rather than fails, so the suite still runs where the weights were never fetched.
CACHE = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen-Image-2.1/snapshots"


def local_weights() -> bool:
    return CACHE.is_dir() and any(CACHE.iterdir())


def job(mode="generate", references=(), **options):
    defaults = {
        "size": "512x512",
        "resolution": "match",
        "steps": 2,
        "guidance": 1.0,
        "strength": 0.4,
        "cfg": 1.0,
        "negative": "",
    }
    return ImageJob(
        mode=mode, prompt="a pear on a table", seed=5, options={**defaults, **options}, references=references
    )


def no_steps(step, total):
    pass


def never_stop():
    return False


@pytest.mark.live
@pytest.mark.skipif(not local_weights(), reason="no local Qwen-Image-2.1")
def test_live_generate_then_edit_then_cancel():
    """Two steps each, so the test is about the engines working rather than about
    image quality. Quality at 1024 is measured by hand, not asserted here."""
    # bf16, the default. The gateway frees one model for the other, which is the
    # path a real run takes and the one a 64 GB machine depends on.
    backend = Qwen21BackendGateway(Qwen21Generator(quantize=None), Qwen21Edit(quantize=None), badge="bf16")
    steps: list[int] = []

    drawn = backend.run(job(), lambda step, total: steps.append(step), never_stop)
    assert isinstance(drawn, ImageResult) and (drawn.width, drawn.height) == (512, 512)
    assert steps == [0, 1, 2]
    assert drawn.png[:4] == b"\x89PNG"

    # One reference, the smallest real edit. The output follows the reference's
    # shape, which is what "match" means and what the old child path was tested on.
    reference = png(512, 384)
    steps.clear()
    edited = backend.run(job("edit", references=(reference,)), lambda step, total: steps.append(step), never_stop)
    assert isinstance(edited, ImageResult) and edited.steps == 2
    assert edited.width / edited.height == pytest.approx(512 / 384, rel=0.05)

    # A cancel has to leave the real mflux loop at the step it lands on. The unit
    # tests raise from a fake loop; this is the only place the real one is proved.
    steps.clear()
    with pytest.raises(Cancelled, match="stopped at step 2"):
        backend.run(
            job(steps=8),
            lambda step, total: steps.append(step),
            lambda: len(steps) >= 2,
        )
    backend.release()
