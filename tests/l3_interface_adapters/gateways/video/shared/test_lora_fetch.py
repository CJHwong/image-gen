import pytest

from studio.l1_entities.errors import StudioError
from studio.l3_interface_adapters.gateways.video.shared.lora_fetch import CARD_NAMES, fetch_lora


def test_a_file_that_is_there_is_not_fetched_again(tmp_path):
    present = tmp_path / "ltx-2.5-22b-ic-lora-deblur-0.9.safetensors"
    present.write_bytes(b"weights")

    assert fetch_lora("deblur", present.name, tmp_path) == present


def test_an_effect_the_studio_does_not_know_is_refused(tmp_path):
    with pytest.raises(StudioError, match="no Lightricks collection"):
        fetch_lora("not-an-effect", "file.safetensors", tmp_path)


def test_a_missing_file_is_fetched_from_the_named_collection(tmp_path, monkeypatch):
    calls = []

    def fake_download(repo_id, filename, local_dir):
        calls.append((repo_id, filename, str(local_dir)))
        target = tmp_path / filename
        target.write_bytes(b"weights")
        return str(target)

    monkeypatch.setattr("huggingface_hub.hf_hub_download", fake_download)

    fetched = fetch_lora("water-simulation", "water.safetensors", tmp_path)

    assert fetched == tmp_path / "water.safetensors"
    assert calls == [("Lightricks/LTX-2.5-22b-IC-LoRA-Water-Simulation", "water.safetensors", str(tmp_path))]


def test_a_refused_fetch_names_the_terms_and_the_login(tmp_path, monkeypatch):
    def refuse(repo_id, filename, local_dir):
        raise RuntimeError("401 Client Error")

    monkeypatch.setattr("huggingface_hub.hf_hub_download", refuse)

    with pytest.raises(StudioError) as failure:
        fetch_lora("restore", "restore.safetensors", tmp_path)

    message = str(failure.value)
    assert "Accept that collection's terms" in message
    assert "hf auth login" in message
    assert "401 Client Error" in message


def test_a_library_that_is_not_installed_is_named(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_hub(name, *args, **kwargs):
        if name == "huggingface_hub":
            raise ImportError("no huggingface_hub")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_hub)

    with pytest.raises(StudioError, match="huggingface-hub is not installed"):
        fetch_lora("deblur", "deblur.safetensors", tmp_path)


def test_every_adapter_names_a_collection():
    assert set(CARD_NAMES) == {
        "day-to-night",
        "water-simulation",
        "clean-plate",
        "deblur",
        "decompression",
        "restore",
        "upscale-2x",
    }
