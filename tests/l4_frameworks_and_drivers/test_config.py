"""studio.toml, read once at start, with the command-line flags on top."""

from pathlib import Path

import pytest

from studio.l4_frameworks_and_drivers.config import ConfigError, load_config

SETTINGS = (
    'default_backend = "qwen21"\n'
    'visible_backends = ["qwen21"]\n'
    "[qwen21]\n"
    "quantize = 0\n"
    'edit_script = "qwen21/qwen21_edit.py"\n'
)


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "studio.toml"
    path.write_text(text)
    return path


def test_the_file_names_the_backend_the_page_opens_with(tmp_path: Path):
    config = load_config(write(tmp_path, SETTINGS))
    assert config.default_backend == "qwen21" and config.visible_backends == ("qwen21",)


def test_a_quantize_of_zero_means_the_full_precision_weights(tmp_path: Path):
    """studio.toml says 0 for bf16, and the engines take it as a quantize of none."""
    assert load_config(write(tmp_path, SETTINGS)).backend("qwen21")["quantize"] is None


def test_a_path_setting_resolves_against_the_settings_file(tmp_path: Path):
    """A path in studio.toml is relative to the file, not to the shell's directory,
    so the server starts the same from any working directory."""
    config = load_config(write(tmp_path, SETTINGS))
    assert config.backend("qwen21")["edit_script"] == str(tmp_path / "qwen21/qwen21_edit.py")


def test_a_tilde_path_setting_expands_to_the_home_directory(tmp_path: Path):
    config = load_config(write(tmp_path, 'default_backend = "flux2"\n[flux2]\nmodel_dir = "~/models"\n'))
    assert config.backend("flux2")["model_dir"] == str(Path("~/models").expanduser())


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
