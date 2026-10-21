"""studio.toml, read once at start, with the command-line flags on top."""

from pathlib import Path

import pytest

from studio.l4_frameworks_and_drivers.config import ConfigError, load_config

SETTINGS = 'default_backend = "qwen21"\nvisible_backends = ["qwen21"]\n[qwen21]\nquantize = 0\n'


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "studio.toml"
    path.write_text(text)
    return path


def test_the_file_names_the_backend_the_page_opens_with(tmp_path: Path):
    config = load_config(write(tmp_path, SETTINGS))
    assert config.default_backend == "qwen21" and config.visible_backends == ("qwen21",)


def test_the_shipping_config_opens_on_turbo_and_offers_no_picker():
    """One model is offered, so the page draws no picker: the file hides nothing, it is the
    default. `--all-backends` is how a person asks for the others, flux2 included."""
    config = load_config(Path(__file__).parents[2] / "studio.toml")

    assert config.default_backend == "qwen21_turbo"
    assert config.visible_backends == ("qwen21_turbo",)


def test_the_shipping_config_loads_the_image_weights_at_full_precision():
    """bf16 by default, because the 2026-10-19 measurement found no level faster than another:
    a quantized level costs accuracy and buys no time. `-q 8` asks for int8 when memory is the
    constraint."""
    config = load_config(Path(__file__).parents[2] / "studio.toml")

    for backend_id in ("qwen21", "qwen21_turbo", "viggle_turbo", "flux2"):
        assert config.backend(backend_id)["quantize"] is None, backend_id


def test_a_quantize_of_zero_means_the_full_precision_weights(tmp_path: Path):
    """studio.toml says 0 for bf16, and the engines take it as a quantize of none."""
    assert load_config(write(tmp_path, SETTINGS)).backend("qwen21")["quantize"] is None


def test_a_path_setting_resolves_against_the_settings_file(tmp_path: Path):
    """A path in studio.toml is relative to the file, not to the shell's directory,
    so the server starts the same from any working directory."""
    config = load_config(write(tmp_path, 'default_backend = "flux2"\n[flux2]\nmodel_dir = "weights/klein"\n'))
    assert config.backend("flux2")["model_dir"] == str(tmp_path / "weights/klein")


def test_a_tilde_path_setting_expands_to_the_home_directory(tmp_path: Path):
    config = load_config(write(tmp_path, 'default_backend = "flux2"\n[flux2]\nmodel_dir = "~/models"\n'))
    assert config.backend("flux2")["model_dir"] == str(Path("~/models").expanduser())


def test_python_path_keeps_a_virtual_environment_symlink(tmp_path: Path):
    python_target = tmp_path / "python-install" / "bin" / "python3"
    python_target.parent.mkdir(parents=True)
    python_target.write_text("python executable")
    python_link = tmp_path / "venv" / "bin" / "python"
    python_link.parent.mkdir(parents=True)
    python_link.symlink_to(python_target)

    config = load_config(write(tmp_path, 'default_backend = "qwen21"\n[mlx_video]\ncli_path = "venv/bin/python"\n'))

    assert config.backend("mlx_video")["cli_path"] == str(python_link)


def test_a_flag_opens_the_page_on_a_backend_the_file_left_out(tmp_path: Path):
    """`--backend flux2` has to add flux2 to the offered list as well. Otherwise
    the page opens on a backend its own picker cannot name."""
    config = load_config(write(tmp_path, SETTINGS), backend="flux2", quantize=8)
    assert config.default_backend == "flux2" and config.visible_backends == ("flux2", "qwen21")
    assert config.backend("flux2")["quantize"] == 8


def test_the_flag_quantize_lands_on_the_backend_the_page_opens_with(tmp_path: Path):
    config = load_config(write(tmp_path, SETTINGS), quantize=4)
    assert config.default_backend == "qwen21" and config.backend("qwen21")["quantize"] == 4


def test_a_file_with_no_visible_list_offers_its_default(tmp_path: Path):
    config = load_config(write(tmp_path, 'default_backend = "flux2"\n'))
    assert config.visible_backends == ("flux2",)


def test_a_setting_that_is_present_comes_back(tmp_path: Path):
    config = load_config(write(tmp_path, SETTINGS))
    assert config.required("qwen21", "quantize") is None  # 0 in the file, read as no quantization


def test_a_missing_setting_is_named_with_its_section(tmp_path: Path):
    """The message has to name the section, because the same key sits under both
    backends and a reader has to know which one to edit."""
    config = load_config(write(tmp_path, SETTINGS))
    with pytest.raises(ConfigError, match=r"no model_dir under \[flux2\]"):
        config.required("flux2", "model_dir")


def test_a_backends_settings_are_a_copy(tmp_path: Path):
    """The composition root reads one section and edits it. A shared dict would
    hand that edit to every later reader of the same section."""
    config = load_config(write(tmp_path, SETTINGS))
    config.backend("qwen21")["quantize"] = 4
    assert config.backend("qwen21")["quantize"] is None


def test_the_shipping_config_opens_voice_on_drama_and_keeps_auk():
    config = load_config(Path(__file__).parents[2] / "studio.toml")

    assert config.default_voice_backend == "drama3"
    assert config.visible_voice_backends == ("drama3", "auk_base", "auk")
