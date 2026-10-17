import sys
import types

import pytest

from studio.l4_frameworks_and_drivers import engines
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.engines import EngineUnavailable, mlx_available
from studio.l4_frameworks_and_drivers.main import create_studio

CONFIG = 'default_backend = "qwen21"\nvisible_backends = ["qwen21"]\n[qwen21]\nquantize = 0\n'


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
    with pytest.raises(EngineUnavailable, match="no MLX GPU is available"):
        create_studio(config)


def test_the_stub_still_builds_where_mlx_is_missing(no_mlx, config):
    """Page work stays possible on a machine that cannot run an engine at all."""
    assert create_studio(config, stub=True).active_capabilities().backend_id == "qwen21"


def test_the_turbo_and_video_stubs_build_without_weights_or_mlx(tmp_path, no_mlx):
    path = tmp_path / "studio.toml"
    path.write_text(
        'default_backend = "qwen21_turbo"\n'
        'visible_backends = ["qwen21_turbo"]\n'
        '[qwen21_turbo]\nquantize = 0\nmodel_dir = "missing-qwen-weights"\n'
        '[ltx25]\npython_path = "missing-python"\nmodel_dir = "missing-ltx-weights"\n'
    )

    studio = create_studio(load_config(path), stub=True)

    assert studio.active_capabilities().backend_id == "qwen21_turbo"
    assert studio.handler.__name__ == "StudioHandler"


def test_the_turbo_stub_builds_where_mlx_cannot_be_imported_at_all(tmp_path, monkeypatch):
    """The availability probe is not the import, and this is the test that tells them
    apart. `no_mlx` above only answers no; a host with no mlx package raises on the
    import, and building a backend that reached for mflux would break the page there.

    A None entry halts the import, which is the trick the test below uses too.
    """
    monkeypatch.setitem(sys.modules, "mlx", None)
    monkeypatch.setitem(sys.modules, "mlx.core", None)
    path = tmp_path / "studio.toml"
    path.write_text(
        'default_backend = "qwen21_turbo"\nvisible_backends = ["qwen21_turbo"]\n'
        '[qwen21_turbo]\nquantize = 0\nmodel_dir = "missing-qwen-weights"\n'
    )

    studio = create_studio(load_config(path), stub=True)

    assert studio.active_capabilities().backend_id == "qwen21_turbo"


def test_the_real_studio_builds_where_mlx_runs(needs_mlx, config):
    assert create_studio(config).active_capabilities().name == "Qwen-Image-2.1"


def fake_mlx(monkeypatch, gpu_available: bool):
    """A stand-in mlx.core, for builds this machine does not have."""
    core = types.ModuleType("mlx.core")
    device_type = types.SimpleNamespace(gpu=object())
    monkeypatch.setattr(core, "DeviceType", device_type, raising=False)
    monkeypatch.setattr(core, "Device", lambda requested_type: requested_type, raising=False)
    monkeypatch.setattr(
        core,
        "is_available",
        lambda requested_device: requested_device is device_type.gpu and gpu_available,
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "mlx", types.ModuleType("mlx"))
    monkeypatch.setitem(sys.modules, "mlx.core", core)


def test_mlx_gpu_is_detected_without_a_metal_namespace(monkeypatch):
    """The generic GPU probe supports CUDA builds that do not expose Metal."""
    fake_mlx(monkeypatch, gpu_available=True)
    assert mlx_available() is True


def test_a_host_with_no_mlx_package_answers_no(monkeypatch):
    """A machine with MLX not installed is a no, not an ImportError. The caller
    gets a decision to act on either way."""
    monkeypatch.setitem(sys.modules, "mlx.core", None)  # a None entry halts the import
    assert mlx_available() is False


def test_mlx_with_no_device_answers_no(monkeypatch):
    fake_mlx(monkeypatch, gpu_available=False)
    assert mlx_available() is False
