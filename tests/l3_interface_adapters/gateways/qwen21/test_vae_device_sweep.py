"""The VAE device sweep: one encode and decode round trip per device and dtype.

The script runs at module scope and needs numpy, torch, diffusers and PIL at module
level, so this test runs the whole file through runpy with diffusers stubbed. The
stub answers a fixed image, and the test asserts the devices and dtypes the sweep
asked for and the three files it wrote.
"""

import runpy
import sys
from unittest.mock import MagicMock, Mock

import pytest
import torch
from PIL import Image

from tests.support import SOURCE_ROOT
from tests.support.heavy import heavy_modules

SWEEP = SOURCE_ROOT / "l3_interface_adapters/gateways/qwen21/vae_device_sweep.py"
ROUNDS = (
    ("mps", torch.bfloat16, "mps bf16"),
    ("mps", torch.float32, "mps fp32"),
    ("cpu", torch.float32, "cpu fp32"),
)


def sweep_stubs():
    """The diffusers classes the sweep loads, and the mocks that record its calls."""
    vae = MagicMock()
    vae.config.z_dim = 16
    vae_class = Mock()
    vae_class.from_pretrained.return_value.to.return_value = vae
    processor = MagicMock()
    processor.postprocess.return_value = [Image.new("RGB", (32, 32), "grey")]
    processor_class = Mock(return_value=processor)
    return (
        {
            "diffusers": {"AutoencoderKLQwenImage21": vae_class},
            "diffusers.image_processor": {"VaeImageProcessor": processor_class},
        },
        vae_class,
        processor_class,
    )


def test_the_sweep_runs_one_round_trip_per_device_and_dtype(tmp_path, monkeypatch, capsys):
    """This sweep is the evidence for the CPU VAE encode: MPS scored a contrast of 17.8
    against 64.2 for the source, at both bf16 and fp32, while CPU fp32 reproduced it."""
    source = tmp_path / "src.png"
    Image.new("RGB", (64, 64), "grey").save(source)
    stubs, vae_class, processor_class = sweep_stubs()
    emptied = Mock()
    monkeypatch.setattr(torch.mps, "empty_cache", emptied)
    monkeypatch.setattr(sys, "argv", [str(SWEEP), str(source)])

    with heavy_modules(stubs):
        runpy.run_path(str(SWEEP), run_name="__main__")

    assert [call.args for call in vae_class.from_pretrained.call_args_list] == [("Qwen/Qwen-Image-2.1",)] * 3
    assert [call.kwargs for call in vae_class.from_pretrained.call_args_list] == [
        {"subfolder": "vae", "torch_dtype": dtype} for _, dtype, _ in ROUNDS
    ]
    assert [call.args for call in vae_class.from_pretrained.return_value.to.call_args_list] == [
        (device,) for device, _, _ in ROUNDS
    ]
    # The latent channel count comes off the loaded config, not out of the air.
    assert processor_class.call_args.kwargs == {"vae_scale_factor": 16, "vae_latent_channels": 16}
    assert emptied.call_count == 2  # the two MPS rounds, never the CPU one
    assert sorted(path.name for path in tmp_path.glob("vae_rt_*.png")) == [
        "vae_rt_cpu_fp32.png",
        "vae_rt_mps_bf16.png",
        "vae_rt_mps_fp32.png",
    ]
    printed = capsys.readouterr().out
    assert "source" in printed and "contrast" in printed and "p1-p99" in printed
    assert all(label in printed for _, _, label in ROUNDS)


def test_the_sweep_refuses_to_run_without_an_image(monkeypatch):
    stubs, _, _ = sweep_stubs()
    monkeypatch.setattr(sys, "argv", [str(SWEEP)])
    with heavy_modules(stubs), pytest.raises(SystemExit, match=r"usage: vae_device_sweep\.py IMAGE\.png"):
        runpy.run_path(str(SWEEP), run_name="__main__")
