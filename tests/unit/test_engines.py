import sys
import types

import pytest

from studio.l4_frameworks_and_drivers import engines
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.engines import EngineUnavailable, mlx_available
from studio.l4_frameworks_and_drivers.main import create_studio

CONFIG = (
    'default_backend = "qwen21"\nvisible_backends = ["qwen21"]\n'
    '[qwen21]\nquantize = 0\nedit_script = "qwen21_edit.py"\n'
)


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "studio.toml"
    path.write_text(CONFIG)
    return load_config(path)


@pytest.fixture
def no_mlx(monkeypatch):
    monkeypatch.setattr(engines, "mlx_available", lambda: False)


@pytest.fixture
def needs_mlx():
    if not mlx_available():
        pytest.skip("this host has no MLX")


def test_a_machine_without_mlx_is_refused_by_name(no_mlx, config):
    with pytest.raises(EngineUnavailable, match="no MLX on this machine"):
        create_studio(config)


def test_the_stub_still_builds_where_mlx_is_missing(no_mlx, config):
    """Page work stays possible on a machine that cannot run an engine at all."""
    assert create_studio(config, stub=True).active_capabilities().backend_id == "qwen21"


def test_the_real_studio_builds_where_mlx_runs(needs_mlx, config):
    assert create_studio(config).active_capabilities().name == "Qwen-Image-2.1"


def fake_mlx(monkeypatch, with_metal: bool):
    """A stand-in mlx.core, for builds this machine does not have."""
    core = types.ModuleType("mlx.core")
    if with_metal:
        monkeypatch.setattr(core, "metal", types.SimpleNamespace(is_available=lambda: False), raising=False)
    monkeypatch.setitem(sys.modules, "mlx", types.ModuleType("mlx"))
    monkeypatch.setitem(sys.modules, "mlx.core", core)


def test_a_build_without_the_metal_module_answers_no(monkeypatch):
    """An mlx build with no metal submodule is a no, not an AttributeError."""
    fake_mlx(monkeypatch, with_metal=False)
    assert mlx_available() is False


def test_mlx_with_no_device_answers_no(monkeypatch):
    fake_mlx(monkeypatch, with_metal=True)
    assert mlx_available() is False
