import pytest

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.png_images import to_pil
from studio.l3_interface_adapters.gateways.qwen21.capabilities import qwen21_capabilities
from studio.l3_interface_adapters.gateways.stub_backend_gateway import StubBackendGateway
from tests.gateways.images import png


def stub():
    return StubBackendGateway(qwen21_capabilities("bf16"), seconds_per_step=0)


def test_the_stub_keeps_the_real_capabilities():
    assert stub().capabilities() == qwen21_capabilities("bf16")


def test_the_stub_reports_every_step_and_makes_the_asked_size():
    steps = []
    job = ImageJob("generate", "a cat", 7, {"size": "1024x576", "steps": 4})
    result = stub().run(job, lambda step, total: steps.append((step, total)), lambda: False)
    assert steps == [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)]
    assert (result.width, result.height, result.seed, result.steps) == (1024, 576, 7, 4)
    assert to_pil(result.png).size == (1024, 576)


def test_the_stub_runs_only_the_steps_a_starting_image_leaves():
    steps = []
    job = ImageJob("generate", "a cat", 7, {"size": "match", "steps": 10, "strength": 0.4}, (png(640, 480),))
    result = stub().run(job, lambda step, total: steps.append((step, total)), lambda: False)
    assert steps[1] == (1, 6) and steps[-1] == (6, 6)
    assert result.width / result.height == pytest.approx(640 / 480, rel=0.02)


def test_the_stub_sizes_an_edit_by_its_resolution():
    job = ImageJob("edit", "make it blue", 7, {"resolution": "512", "steps": 2}, (png(640, 480),))
    result = stub().run(job, lambda step, total: None, lambda: False)
    assert (result.width, result.height) == (512, 512)


def test_the_stub_stops_when_asked():
    job = ImageJob("generate", "a cat", 7, {"size": "512x512", "steps": 4})
    with pytest.raises(Cancelled, match=r"stopped at step 1$"):
        stub().run(job, lambda step, total: None, lambda: True)
