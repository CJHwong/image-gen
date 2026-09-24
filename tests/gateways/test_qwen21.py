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


def test_the_step_hook_counts_only_the_steps_that_run():
    """With a starting image, mflux skips the start of the schedule. 40 steps at strength 0.4
    run steps 16 to 39, so the first to arrive is step 1 of 24, not step 17 of 40."""

    class Img2ImgConfig:
        init_time_step = 16
        num_inference_steps = 40

    hook = StepHook()
    steps = []
    with hook.watch(lambda step, total: steps.append((step, total)), lambda: False, total=40):
        for t in range(16, 40):
            hook.call_in_loop(t, None, None, None, Img2ImgConfig(), None)
    assert steps[0] == (1, 24) and steps[-1] == (24, 24)
    with (
        hook.watch(lambda step, total: None, lambda: True, total=40),
        pytest.raises(Cancelled, match=r"stopped at step 5$"),
    ):
        hook.call_in_loop(20, None, None, None, Img2ImgConfig(), None)


@pytest.mark.parametrize("sizes", [qwen21_sizes, flux2_sizes], ids=["qwen21", "flux2"])
def test_every_size_keeps_its_named_ratio_on_the_16_pixel_grid(sizes):
    """Within 1%, because the largest tier keeps the model's own sizes: 1664 x 928 is not quite 16:9."""
    for label, width, height in (size for size in sizes if isinstance(size, tuple)):
        named = re.search(r"\((\d+):(\d+)\)", label)
        across, down = (int(named[1]), int(named[2])) if named else (1, 1)
        assert width % 16 == 0 and height % 16 == 0, label
        assert abs(width / height - across / down) <= 0.01 * across / down, label


def test_a_negative_prompt_names_the_guidance_it_needs():
    caps = Qwen21BackendGateway(None, None, badge="bf16").capabilities()
    for mode_id, scale_id in (("generate", "guidance"), ("edit", "cfg")):
        params = {param.id: param for param in caps.mode(mode_id).params}
        assert "negative" in params
        scale = params[scale_id]
        assert scale.with_negative == 2.5 and scale.maximum == 10, mode_id


def test_only_real_person_carries_an_avoid_part():
    looks = Qwen21BackendGateway(None, None, badge="bf16").capabilities().mode("generate").looks
    avoids = {row.name: dict(row.avoids) for row in looks if row.avoids}
    assert list(avoids) == ["Realism"] and list(avoids["Realism"]) == ["Real person"]
    assert "airbrushed skin" in avoids["Realism"]["Real person"]


def test_qwen21_offers_the_templates_it_passed():
    caps = Qwen21BackendGateway(None, None, badge="bf16").capabilities()
    generate = [template.name for template in caps.mode("generate").templates]
    edit = [template.name for template in caps.mode("edit").templates]
    assert generate[-2:] == ["Deadpan absurdity", "Banner"] and len(generate) == 7
    assert edit[-2:] == ["Alternate reality", "Add an object"] and len(edit) == 5


def test_the_look_rows_go_style_then_shot_then_subject():
    looks = Qwen21BackendGateway(None, None, badge="bf16").capabilities().mode("generate").looks
    assert [row.name for row in looks] == [
        "Medium", "Film", "Color", "Light", "Camera", "Room for text", "Realism", "Portrait",
    ]  # fmt: skip
    film = dict(looks[1].options)
    assert list(film) == ["Portra 400", "Fuji 400H", "Ektachrome", "Black and white"]
    # Each film stock lives in the Film row only, so one pick per row keeps two stocks apart.
    for row in looks[:1] + looks[2:]:
        for _, sentence in row.options:
            assert not any(stock in sentence for stock in ("Portra", "Tri-X", "Fuji", "Ektachrome")), row.name
