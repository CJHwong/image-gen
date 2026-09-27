import os

import pytest

from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.flux2.flux2_backend_gateway import Flux2BackendGateway
from studio.l3_interface_adapters.gateways.flux2.klein_models import KleinModels
from tests.support.images import png


def job(mode="generate", references=(), **options):
    defaults = {"size": "1024x1024", "steps": 8, "guidance": 4.0}
    if mode == "generate":
        defaults["strength"] = 0.4
    return ImageJob(mode=mode, prompt="a pear", seed=5, options={**defaults, **options}, references=references)


class Models:
    """The engine side, which the backend only forwards to."""

    def __init__(self):
        self.calls = []

    def load(self):
        self.calls.append("load")

    def run(self, the_job, on_step, should_stop):
        self.calls.append(("run", the_job))
        return ImageResult(png=b"png", width=8, height=8, seed=the_job.seed, steps=1)

    def release(self):
        self.calls.append("release")


def test_the_page_sees_the_flux2_form_and_its_badge():
    caps = Flux2BackendGateway(None, badge="int8").capabilities()
    assert (caps.backend_id, caps.badge) == ("flux2", "int8")
    assert [mode.id for mode in caps.modes] == ["generate", "edit"]


def test_every_call_reaches_the_engine():
    models = Models()
    backend = Flux2BackendGateway(models, badge="int8")
    the_job = job(size="16x16")
    backend.load()
    result = backend.run(the_job, lambda step, total: None, lambda: False)
    backend.release()
    assert models.calls == ["load", ("run", the_job), "release"]
    assert result.steps == 1


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
