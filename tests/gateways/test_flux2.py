import os

import pytest

from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.flux2.capabilities import flux2_capabilities
from studio.l3_interface_adapters.gateways.flux2.flux2_backend_gateway import Flux2BackendGateway
from studio.l3_interface_adapters.gateways.flux2.klein_models import KleinModels, edit_kwargs, generate_kwargs
from studio.l3_interface_adapters.gateways.prompt_aids import pick_looks, pick_templates
from tests.gateways.images import png


def job(mode="generate", references=(), **options):
    defaults = {"size": "1024x1024", "steps": 8, "guidance": 4.0}
    if mode == "generate":
        defaults["strength"] = 0.4
    return ImageJob(mode=mode, prompt="a pear", seed=5, options={**defaults, **options}, references=references)


def test_generate_maps_the_form_to_mflux():
    assert generate_kwargs(job(size="1280x720", guidance=2.5)) == {
        "seed": 5,
        "prompt": "a pear",
        "width": 1280,
        "height": 720,
        "num_inference_steps": 8,
        "guidance": 2.5,
    }


def test_a_generate_reference_brings_its_strength():
    kwargs = generate_kwargs(job(references=(png(64, 48),), strength=0.6))
    assert kwargs["image_strength"] == 0.6 and kwargs["image_path"].size == (64, 48)


def test_edit_passes_every_reference_and_matches_the_last_shape():
    kwargs = edit_kwargs(job("edit", references=(png(32, 32), png(1600, 900)), size="match"))
    assert [image.size for image in kwargs["image_paths"]] == [(32, 32), (1600, 900)]
    assert (kwargs["width"], kwargs["height"]) == (1360, 768)
    assert "image_strength" not in kwargs


class FakeModel:
    def __init__(self, mode, log):
        self.mode, self.log = mode, log

    def generate_image(self, **kwargs):
        self.log.append(f"{self.mode} run")
        from PIL import Image

        class Generated:
            image = Image.new("RGB", (kwargs["width"], kwargs["height"]))

        return Generated()


def test_one_model_at_a_time():
    log = []
    models = KleinModels("dir", 8, build=lambda mode, *_: log.append(f"build {mode}") or FakeModel(mode, log))
    backend = Flux2BackendGateway(models, badge="int8")
    backend.load()
    backend.load()

    def run(the_job):
        return backend.run(the_job, lambda step, total: None, lambda: False)

    run(job(size="16x16"))
    run(job("edit", references=(png(8, 8),), size="16x16"))
    run(job("edit", references=(png(8, 8),), size="16x16"))
    assert log == ["build generate", "generate run", "build edit", "edit run", "edit run"]


def test_the_page_sees_no_negative_prompt():
    caps = Flux2BackendGateway(None, badge="int8").capabilities()
    for mode in caps.modes:
        assert "negative" not in [param.id for param in mode.params]
    assert [param.default for param in caps.mode("edit").params if param.id == "size"] == ["match"]
    assert [param.default for param in caps.mode("generate").params if param.id == "size"] == ["1024x1024"]


MODEL_DIR = os.path.expanduser("~/Library/Caches/models/mflux-klein-base-9b-uncensored")


@pytest.mark.live
@pytest.mark.skipif(not os.path.isdir(MODEL_DIR), reason="no local klein-base-9b")
def test_live_generate_then_edit_then_cancel():
    from studio.l1_entities.errors import Cancelled

    backend = Flux2BackendGateway(KleinModels(MODEL_DIR, 8), badge="int8")
    steps = []
    result = backend.run(job(size="512x512", steps=4), lambda step, total: steps.append(step), lambda: False)
    assert isinstance(result, ImageResult) and (result.width, result.height) == (512, 512)
    assert steps == [0, 1, 2, 3, 4]
    reference = png(512, 384)
    edited = backend.run(job("edit", references=(reference,), size="match", steps=2), lambda *_: None, lambda: False)
    assert edited.width / edited.height == pytest.approx(512 / 384, rel=0.02)
    with pytest.raises(Cancelled, match="stopped at step 2"):
        backend.run(job(size="512x512", steps=4), lambda step, total: steps.append(step), lambda: len(steps) > 6)
    backend.release()


def test_flux2_offers_only_the_prompt_aids_it_passed():
    generate, edit = flux2_capabilities("int8").modes
    offered = {row.name: [name for name, _ in row.options] for row in generate.looks}
    assert offered == {
        "Medium": ["Watercolor", "3D render"],
        "Film": ["Portra 400", "Black and white"],
        "Color": ["Vivid"],
        "Light": ["Studio", "Night with neon"],
        "Camera": ["Wide 24mm", "Top-down"],
        "Room for text": ["Left", "Top"],
    }
    black_and_white = dict(generate.looks[1].options)["Black and white"]
    assert "Kodak" not in black_and_white  # flux2 prints a named film stock on the frame
    assert [template.name for template in generate.templates] == [
        "Portrait photo",
        "Product shot",
        "Landscape",
        "Poster with text",
        "Illustration",
    ]
    assert [template.name for template in edit.templates] == [
        "Change a color or material",
        "Replace the background",
        "Add text",
    ]


def test_a_look_that_does_not_exist_is_refused():
    with pytest.raises(ValueError, match="Colour"):
        pick_looks({"Colour": ("Vivid",)})
    with pytest.raises(ValueError, match="Sepia"):
        pick_looks({"Color": ("Sepia",)})


def test_a_template_that_does_not_exist_is_refused():
    with pytest.raises(ValueError, match="Poster"):
        pick_templates(("Poster",))


def test_the_estimate_says_it_was_measured_with_two_passes():
    caps = Flux2BackendGateway(None, badge="int8").capabilities()
    assert all(mode.estimate.two_pass for mode in caps.modes)  # measured at guidance 4


def test_a_picked_option_keeps_its_avoid_part():
    light, realism = pick_looks({"Realism": ("Real person",), "Light": ("Studio",)})
    assert [name for name, _ in realism.avoids] == ["Real person"] and light.avoids == ()
