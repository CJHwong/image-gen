"""The real Turbo weights, on the sigma table the checkpoint ships.

Two things here can only be proved with the real engine. The first is that the
table this repo registered is the checkpoint's own: `model_index.json` is read and
compared, so a republished checkpoint cannot drift away from the constant. The
second is that mflux accepts the registered name and samples it, on both paths,
including the edit path whose `Config` has to be patched because its call takes no
scheduler argument.

The unit tests beside this file stub both engines, so a break inside mflux reads
exactly like a break this repo caused. This is the test that tells the two apart.
"""

import json
from pathlib import Path

import pytest

from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.official_qwen_turbo_backend_gateway import (
    OfficialQwenTurboBackendGateway,
)
from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import (
    active_mlx_memory,
    official_turbo_model_config,
)
from studio.l3_interface_adapters.gateways.image.shared.qwen21_turbo_schedule import (
    SCHEDULER_NAME,
    SIGMA_NODES,
    STEPS,
    official_turbo_schedule,
    register_schedule,
)
from tests.support.images import png

# Where studio.toml points [qwen21_turbo].model_dir. A machine without the
# checkpoint skips rather than fails, so the suite runs where it was never fetched.
MODEL_DIR = Path.home() / "Library/Caches/models/qwen-image-2.1-turbo"
CHECKPOINT_FILES = (
    "model_index.json",
    "transformer/config.json",
    "text_encoder/model.safetensors",
)


def local_weights() -> bool:
    return all((MODEL_DIR / name).is_file() for name in CHECKPOINT_FILES)


def job(mode="generate", references=(), **options):
    defaults = {
        "size": "512x512",
        "resolution": "match",
        "steps": STEPS,
        "guidance": 1.0,
        "strength": 0.4,
        "cfg": 1.0,
        "negative": "",
    }
    return ImageJob(
        mode=mode, prompt="a pear on a table", seed=5, options={**defaults, **options}, references=references
    )


def never_stop():
    return False


@pytest.mark.live
@pytest.mark.skipif(not local_weights(), reason="no official Turbo checkpoint")
def test_the_registered_table_is_the_one_the_checkpoint_ships():
    shipped = json.loads((MODEL_DIR / "model_index.json").read_text(encoding="utf-8"))["sample_sigmas"]

    assert tuple(float(value) for value in shipped) == SIGMA_NODES
    assert len(shipped) == STEPS


@pytest.mark.live
@pytest.mark.skipif(not local_weights(), reason="no official Turbo checkpoint")
def test_mflux_builds_the_shipped_table_from_the_registered_name():
    """The edit path cannot be handed a scheduler, so it takes the patched default.
    Both are checked against the real mflux rather than a stub."""
    from mflux.models.common.config.config import Config

    register_schedule()
    with official_turbo_schedule():
        patched = Config(model_config=official_turbo_model_config(), num_inference_steps=STEPS, height=512, width=512)
        assert [round(float(value), 6) for value in patched.scheduler.sigmas.tolist()] == [
            *SIGMA_NODES,
            0.0,
        ]

    direct = Config(
        model_config=official_turbo_model_config(),
        num_inference_steps=STEPS,
        height=512,
        width=512,
        scheduler=SCHEDULER_NAME,
    )
    assert [round(float(value), 6) for value in direct.scheduler.sigmas.tolist()] == [*SIGMA_NODES, 0.0]


@pytest.mark.live
@pytest.mark.skipif(not local_weights(), reason="no official Turbo checkpoint")
def test_live_turbo_generates_and_edits_on_the_shipped_table():
    """One generate and one edit, on the real weights. The step count is asserted
    because it is the table's: eight nodes means eight steps and no other count."""
    backend = OfficialQwenTurboBackendGateway(
        Qwen21Generator(None, model_path=str(MODEL_DIR), scheduler=SCHEDULER_NAME),
        Qwen21Edit(None, model_path=str(MODEL_DIR)),
        badge="bf16",
        model_dir=str(MODEL_DIR),
        memory_scope=active_mlx_memory,
    )
    steps: list[int] = []
    drawn = backend.run(job(), lambda step, total: steps.append(step), never_stop)

    assert isinstance(drawn, ImageResult) and (drawn.width, drawn.height) == (512, 512)
    assert steps == list(range(STEPS + 1))
    assert drawn.png[:4] == b"\x89PNG"

    # The edit path is the one the patch exists for: mflux's edit call takes no
    # scheduler argument, so without it this run would sample the linear table.
    reference = png(512, 384)
    edited = backend.run(job("edit", references=(reference,)), lambda step, total: None, never_stop)

    assert isinstance(edited, ImageResult) and edited.steps == STEPS
    assert edited.width / edited.height == pytest.approx(512 / 384, rel=0.05)
    backend.release()
