import base64
import re

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.flux2.capabilities import SIZES as flux2_sizes
from studio.l3_interface_adapters.gateways.mflux_runtime import StepHook
from studio.l3_interface_adapters.gateways.qwen21.capabilities import SIZES as qwen21_sizes
from studio.l3_interface_adapters.gateways.qwen21.edit import edit_payload
from studio.l3_interface_adapters.gateways.qwen21.generator import generate_kwargs
from studio.l3_interface_adapters.gateways.qwen21.qwen21_backend_gateway import Qwen21BackendGateway
from tests.gateways.images import png


def job(mode="generate", references=(), **options):
    defaults = {
        "generate": {"size": "1024x1024", "steps": 8, "guidance": 1.0, "strength": 0.4, "negative": ""},
        "edit": {"resolution": "match", "steps": 8, "cfg": 1.0, "negative": ""},
    }[mode]
    return ImageJob(mode=mode, prompt="a pear", seed=5, options={**defaults, **options}, references=references)


def test_generate_maps_the_form_to_mflux():
    kwargs = generate_kwargs(job(size="768x432", negative="blur", guidance=2.5))
    assert kwargs == {
        "seed": 5,
        "prompt": "a pear",
        "negative_prompt": "blur",
        "width": 768,
        "height": 432,
        "num_inference_steps": 8,
        "guidance": 2.5,
    }


def test_a_reference_brings_its_strength_and_is_passed_as_an_image():
    kwargs = generate_kwargs(job(references=(png(64, 48),), strength=0.6))
    assert kwargs["image_strength"] == 0.6
    assert kwargs["image_path"].size == (64, 48)


def test_match_keeps_the_reference_shape_at_one_megapixel():
    kwargs = generate_kwargs(job(references=(png(1600, 900),), size="match"))
    assert (kwargs["width"], kwargs["height"]) == (1360, 768)
    assert generate_kwargs(job(size="match"))["width"] == 1024  # no reference: the square default


def test_edit_sends_pngs_and_sizes_from_the_last_reference():
    payload = edit_payload(job("edit", references=(png(32, 32), png(2560, 1440))))
    assert payload["output_resolution"] == 1328  # the cap, not 1920
    assert len(payload["images"]) == 2 and base64.b64decode(payload["images"][0])[:4] == b"\x89PNG"
    assert payload["seed"] == 5 and payload["true_cfg_scale"] == 1.0 and payload["negative_prompt"] is None
    assert edit_payload(job("edit", references=(png(32, 32),), resolution="768"))["output_resolution"] == 768


class Recorder:
    def __init__(self, name, log):
        self.name, self.log = name, log

    def run(self, the_job, on_step, should_stop):
        self.log.append(f"{self.name} run")
        return ImageResult(png=b"", width=1, height=1, seed=the_job.seed, steps=1)

    def release(self):
        self.log.append(f"{self.name} release")

    def load(self):
        self.log.append(f"{self.name} load")


def test_only_one_engine_holds_memory_at_a_time():
    log = []
    backend = Qwen21BackendGateway(Recorder("mflux", log), Recorder("edit", log), badge="bf16")
    backend.run(job("edit", references=(png(8, 8),)), None, None)
    backend.run(job(), None, None)
    assert log == ["mflux release", "edit run", "edit release", "mflux run"]


def test_the_step_hook_reports_and_cancels():
    hook = StepHook()
    steps = []
    with hook.watch(lambda step, total: steps.append((step, total)), lambda: len(steps) >= 2, total=8):
        hook.call_in_loop(0, None, None, None, None, None)
        hook.call_in_loop(1, None, None, None, None, None)
        with pytest.raises(Cancelled, match="stopped at step 3"):
            hook.call_in_loop(2, None, None, None, None, None)
    assert steps == [(1, 8), (2, 8)]
    hook.call_in_loop(3, None, None, None, None, None)  # no run watched: nothing happens


@pytest.mark.parametrize("sizes", [qwen21_sizes, flux2_sizes], ids=["qwen21", "flux2"])
def test_every_size_keeps_its_named_ratio_on_the_16_pixel_grid(sizes):
    """Within 1%, because the largest tier keeps the model's own sizes: 1664 x 928 is not quite 16:9."""
    for label, width, height in (size for size in sizes if isinstance(size, tuple)):
        named = re.search(r"\((\d+):(\d+)\)", label)
        across, down = (int(named[1]), int(named[2])) if named else (1, 1)
        assert width % 16 == 0 and height % 16 == 0, label
        assert abs(width / height - across / down) <= 0.01 * across / down, label
