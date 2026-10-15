import pytest

from studio.l1_entities.errors import StudioError
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.qwen21_turbo.official_qwen_turbo_backend_gateway import (
    OfficialQwenTurboBackendGateway,
)


class FakeModel:
    def __init__(self, result=None):
        self.events = []
        self.result = result or ImageResult(b"png", 32, 32, 7, 8)

    def load(self):
        self.events.append("load")

    def release(self):
        self.events.append("release")

    def run(self, job, on_step, should_stop):
        self.events.append(("run", job.mode))
        return self.result


def checkpoint(root):
    for relative_path in (
        "model_index.json",
        "scheduler/scheduler_config.json",
        "processor/processor_config.json",
        "processor/tokenizer.json",
        "vae/config.json",
        "vae/diffusion_pytorch_model.safetensors",
        "transformer/config.json",
        "transformer/diffusion_pytorch_model.safetensors",
        "text_encoder/config.json",
        "text_encoder/model.safetensors",
    ):
        item = root / relative_path
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_bytes(b"local checkpoint fixture")


def image_job(mode):
    return ImageJob(mode, "a cup", 7, {"steps": 8, "size": "512x512", "resolution": "match"})


def test_gateway_checks_local_checkpoint_before_loading_any_model(tmp_path):
    generator, edit = FakeModel(), FakeModel()
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path / "missing"))

    with pytest.raises(StudioError, match="local checkpoint is missing"):
        gateway.load()

    assert generator.events == []


def test_gateway_names_missing_checkpoint_components(tmp_path):
    generator, edit = FakeModel(), FakeModel()
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path))

    with pytest.raises(StudioError, match=r"model_index\.json") as error:
        gateway.load()

    assert "transformer/*.safetensors" in str(error.value)
    assert generator.events == []


def test_gateway_loads_official_local_checkpoint(tmp_path):
    checkpoint(tmp_path)
    generator, edit = FakeModel(), FakeModel()
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path))

    gateway.load()

    assert generator.events == ["load"]


def test_gateway_frees_the_other_model_before_running_generate_and_edit(tmp_path):
    checkpoint(tmp_path)
    generator, edit = FakeModel(), FakeModel()
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path))

    assert gateway.run(image_job("generate"), lambda *_: None, lambda: False).png == b"png"
    assert gateway.run(image_job("edit"), lambda *_: None, lambda: False).png == b"png"
    gateway.release()

    assert generator.events == [("run", "generate"), "release", "release"]
    assert edit.events == ["release", ("run", "edit"), "release"]
