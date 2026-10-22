import json
import sys
from types import ModuleType
from unittest.mock import Mock

import numpy as np
import pytest
from safetensors.numpy import save_file

from studio.l1_entities.errors import StudioError
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.image.qwen21_turbo import (
    official_qwen_turbo_backend_gateway as gateway_module,
)
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.official_qwen_turbo_backend_gateway import (
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
        if relative_path == "text_encoder/model.safetensors":
            save_file({"model.language_model.embed_tokens.weight": np.zeros((1,), dtype=np.float32)}, str(item))
        else:
            item.write_bytes(b"local checkpoint fixture")


def image_job(mode):
    return ImageJob(mode, "a cup", 7, {"steps": 8, "size": "512x512", "resolution": "match"})


def test_gateway_downloads_official_checkpoint_before_loading_any_model(tmp_path, monkeypatch):
    generator, edit = FakeModel(), FakeModel()
    model_dir = tmp_path / "missing"
    downloads = []

    def download_checkpoint(destination):
        downloads.append(destination)
        checkpoint(destination)

    monkeypatch.setattr(gateway_module, "download_official_checkpoint", download_checkpoint)
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(model_dir))

    gateway.load()

    assert downloads == [model_dir]
    assert generator.events == ["load"]


def test_gateway_downloads_official_checkpoint_on_first_generate_run(tmp_path, monkeypatch):
    generator, edit = FakeModel(), FakeModel()
    model_dir = tmp_path / "missing"
    downloads = []

    def download_checkpoint(destination):
        downloads.append(destination)
        checkpoint(destination)

    monkeypatch.setattr(gateway_module, "download_official_checkpoint", download_checkpoint)
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(model_dir))

    gateway.run(image_job("generate"), lambda *_: None, lambda: False)
    gateway.run(image_job("generate"), lambda *_: None, lambda: False)

    assert downloads == [model_dir]
    assert generator.events == [("run", "generate"), ("run", "generate")]


def test_gateway_downloads_official_checkpoint_on_first_edit_run(tmp_path, monkeypatch):
    generator, edit = FakeModel(), FakeModel()
    model_dir = tmp_path / "missing"
    downloads = []

    def download_checkpoint(destination):
        downloads.append(destination)
        checkpoint(destination)

    monkeypatch.setattr(gateway_module, "download_official_checkpoint", download_checkpoint)
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(model_dir))

    gateway.run(image_job("edit"), lambda *_: None, lambda: False)

    assert downloads == [model_dir]
    assert generator.events == ["release"]
    assert edit.events == [("run", "edit")]


def test_gateway_reports_download_failure_without_loading_a_model(tmp_path, monkeypatch):
    generator, edit = FakeModel(), FakeModel()
    monkeypatch.setattr(
        gateway_module,
        "download_official_checkpoint",
        Mock(side_effect=StudioError("Could not download official Qwen Turbo")),
    )
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path / "missing"))

    with pytest.raises(StudioError, match="Could not download official Qwen Turbo"):
        gateway.load()

    assert generator.events == []


def test_gateway_names_components_still_missing_after_download(tmp_path, monkeypatch):
    generator, edit = FakeModel(), FakeModel()
    monkeypatch.setattr(gateway_module, "download_official_checkpoint", lambda _destination: None)
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path))

    with pytest.raises(StudioError, match=r"download at .* is incomplete: model_index\.json") as error:
        gateway.load()

    assert "transformer/*.safetensors" in str(error.value)
    assert generator.events == []


def test_gateway_loads_official_local_checkpoint(tmp_path):
    checkpoint(tmp_path)
    generator, edit = FakeModel(), FakeModel()
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path))

    gateway.load()

    assert generator.events == ["load"]


def test_gateway_indexes_the_official_single_file_text_encoder(tmp_path):
    checkpoint(tmp_path)
    weights_path = tmp_path / "text_encoder/model.safetensors"
    weights_before = weights_path.read_bytes()
    gateway = OfficialQwenTurboBackendGateway(FakeModel(), FakeModel(), "bf16", str(tmp_path))

    gateway.load()

    index = json.loads((tmp_path / "text_encoder/model.safetensors.index.json").read_text())
    assert index["weight_map"] == {"model.language_model.embed_tokens.weight": "model.safetensors"}
    assert weights_path.read_bytes() == weights_before


def test_gateway_keeps_an_existing_text_encoder_index(tmp_path):
    checkpoint(tmp_path)
    index_path = tmp_path / "text_encoder/model.safetensors.index.json"
    original_index = '{"weight_map":{"model.language_model.embed_tokens.weight":"model.safetensors"}}'
    index_path.write_text(original_index)
    generator = FakeModel()
    gateway = OfficialQwenTurboBackendGateway(generator, FakeModel(), "bf16", str(tmp_path))

    gateway.load()

    assert index_path.read_text() == original_index
    assert generator.events == ["load"]


def test_gateway_rebuilds_a_stale_text_encoder_index(tmp_path):
    checkpoint(tmp_path)
    index_path = tmp_path / "text_encoder/model.safetensors.index.json"
    index_path.write_text('{"weight_map":{"bad.key":"../outside.safetensors"}}')
    gateway = OfficialQwenTurboBackendGateway(FakeModel(), FakeModel(), "bf16", str(tmp_path))

    gateway.load()

    index = json.loads(index_path.read_text())
    assert index["weight_map"] == {"model.language_model.embed_tokens.weight": "model.safetensors"}


def test_gateway_rebuilds_a_malformed_text_encoder_index(tmp_path):
    checkpoint(tmp_path)
    index_path = tmp_path / "text_encoder/model.safetensors.index.json"
    index_path.write_text("not json")
    gateway = OfficialQwenTurboBackendGateway(FakeModel(), FakeModel(), "bf16", str(tmp_path))

    gateway.load()

    index = json.loads(index_path.read_text())
    assert index["weight_map"] == {"model.language_model.embed_tokens.weight": "model.safetensors"}


def test_gateway_rebuilds_a_non_utf8_text_encoder_index(tmp_path):
    checkpoint(tmp_path)
    index_path = tmp_path / "text_encoder/model.safetensors.index.json"
    index_path.write_bytes(b"\xff")
    gateway = OfficialQwenTurboBackendGateway(FakeModel(), FakeModel(), "bf16", str(tmp_path))

    gateway.load()

    index = json.loads(index_path.read_text())
    assert index["weight_map"] == {"model.language_model.embed_tokens.weight": "model.safetensors"}


def test_gateway_rebuilds_a_non_object_text_encoder_index(tmp_path):
    checkpoint(tmp_path)
    index_path = tmp_path / "text_encoder/model.safetensors.index.json"
    index_path.write_text("[]")
    gateway = OfficialQwenTurboBackendGateway(FakeModel(), FakeModel(), "bf16", str(tmp_path))

    gateway.load()

    index = json.loads(index_path.read_text())
    assert index["weight_map"] == {"model.language_model.embed_tokens.weight": "model.safetensors"}


def test_gateway_replaces_a_symlink_without_overwriting_its_target(tmp_path):
    checkpoint(tmp_path)
    index_path = tmp_path / "text_encoder/model.safetensors.index.json"
    external_index = tmp_path / "external-index.json"
    external_index.write_text("keep this file")
    index_path.symlink_to(external_index)
    gateway = OfficialQwenTurboBackendGateway(FakeModel(), FakeModel(), "bf16", str(tmp_path))

    gateway.load()

    index = json.loads(index_path.read_text())
    assert index["weight_map"] == {"model.language_model.embed_tokens.weight": "model.safetensors"}
    assert not index_path.is_symlink()
    assert external_index.read_text() == "keep this file"


def test_gateway_rejects_an_empty_text_encoder(tmp_path):
    checkpoint(tmp_path)
    weights_path = tmp_path / "text_encoder/model.safetensors"
    save_file({}, str(weights_path))
    generator = FakeModel()
    gateway = OfficialQwenTurboBackendGateway(generator, FakeModel(), "bf16", str(tmp_path))

    with pytest.raises(StudioError, match="text encoder has no weights"):
        gateway.load()

    assert generator.events == []


def test_downloader_fetches_only_the_official_qwen_turbo_repo(tmp_path, monkeypatch):
    hub = ModuleType("huggingface_hub")
    hub.__dict__["snapshot_download"] = Mock()
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    gateway_module.download_official_checkpoint(tmp_path / "weights")

    hub.__dict__["snapshot_download"].assert_called_once_with(
        repo_id="Qwen/Qwen-Image-2.1-Turbo",
        local_dir=str(tmp_path / "weights"),
    )


def test_downloader_reports_huggingface_errors(tmp_path, monkeypatch):
    hub = ModuleType("huggingface_hub")
    hub.__dict__["snapshot_download"] = Mock(side_effect=OSError("network unavailable"))
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    with pytest.raises(StudioError, match=r"Could not download official Qwen Turbo.*network unavailable"):
        gateway_module.download_official_checkpoint(tmp_path / "weights")


def test_gateway_frees_the_other_model_before_running_generate_and_edit(tmp_path):
    checkpoint(tmp_path)
    generator, edit = FakeModel(), FakeModel()
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path))

    assert gateway.run(image_job("generate"), lambda *_: None, lambda: False).png == b"png"
    assert gateway.run(image_job("edit"), lambda *_: None, lambda: False).png == b"png"
    gateway.release()

    assert generator.events == [("run", "generate"), "release", "release"]
    assert edit.events == ["release", ("run", "edit"), "release"]


def test_generate_batch_prepares_prompts_before_the_first_run(tmp_path, monkeypatch):
    generator, edit = Mock(), Mock()
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path))
    ensure = Mock()
    monkeypatch.setattr(gateway, "_ensure_checkpoint", ensure)
    register = Mock()
    monkeypatch.setattr(gateway_module, "register_schedule", register)
    jobs = [image_job("generate"), image_job("generate")]

    def cancelled():
        return False

    assert gateway.capabilities().backend_id == "qwen21_turbo"
    gateway.prepare_batch(jobs, cancelled)
    ensure.assert_called_once_with()
    register.assert_called_once_with()
    edit.release.assert_called_once_with()
    generator.prepare_batch.assert_called_once_with(jobs, cancelled)


@pytest.mark.parametrize("modes", [[], ["edit"], ["generate", "edit"]])
def test_other_batches_keep_sequential_model_loading(tmp_path, modes):
    generator, edit = Mock(), Mock()
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path))
    gateway.prepare_batch([image_job(mode) for mode in modes], lambda: False)
    generator.prepare_batch.assert_not_called()
    edit.release.assert_not_called()


@pytest.mark.parametrize("mode", ["generate", "edit", "batch"])
@pytest.mark.parametrize("failure", [False, True])
def test_active_memory_covers_engine_work_and_unwinds_on_failure(mode, failure, tmp_path, monkeypatch):
    from contextlib import contextmanager

    from studio.l1_entities.errors import Cancelled

    events = []

    @contextmanager
    def memory_scope():
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    def work(*_args):
        assert events == ["enter"]
        if failure:
            raise Cancelled("stopped")
        return "result"

    generator, edit = Mock(), Mock()
    generator.run.side_effect = edit.run.side_effect = generator.prepare_batch.side_effect = work
    gateway = OfficialQwenTurboBackendGateway(generator, edit, "bf16", str(tmp_path), memory_scope=memory_scope)
    monkeypatch.setattr(gateway, "_ensure_checkpoint", lambda: None)
    monkeypatch.setattr(gateway_module, "register_schedule", lambda: None)
    monkeypatch.setattr(gateway_module, "official_turbo_schedule", memory_scope_for_schedule)

    def execute():
        if mode == "batch":
            gateway.prepare_batch([image_job("generate")], lambda: False)
        else:
            assert gateway.run(image_job(mode), lambda *_: None, lambda: False) == "result"

    if failure:
        with pytest.raises(Cancelled):
            execute()
    else:
        execute()
    assert events == ["enter", "exit"]


def memory_scope_for_schedule():
    from contextlib import nullcontext

    return nullcontext()
