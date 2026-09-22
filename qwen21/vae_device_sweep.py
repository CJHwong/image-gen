#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "diffusers @ git+https://github.com/huggingface/diffusers@9f1246971270c84dcbe71233edb7a519596a5d02",
#     "torch>=2.4.0", "torchvision", "transformers>=4.57.0", "accelerate", "pillow", "sentencepiece", "numpy",
# ]
# ///
"""Sweep a VAE encode/decode round trip over device and dtype.

No transformer and no pipeline, so the VAE is the only thing under test.
Usage: ./vae_device_sweep.py IMAGE.png
See MPS-VAE-ENCODE.md for the results this produced and what they mean.
"""
import os
import sys
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import pathlib

import torch, numpy as np
from PIL import Image
from diffusers import AutoencoderKLQwenImage21
from diffusers.image_processor import VaeImageProcessor

if len(sys.argv) != 2:
    sys.exit("usage: vae_device_sweep.py IMAGE.png")
SRC = pathlib.Path(sys.argv[1])
src = Image.open(SRC).convert("RGBA")

def score(pil, label):
    a = np.asarray(pil.convert("RGB"), dtype=np.float32); g = a.mean(axis=2)
    print(f"{label:28s} mean {g.mean():6.1f}  contrast {g.std():5.1f}  "
          f"p1-p99 {np.percentile(g,1):5.1f}-{np.percentile(g,99):5.1f}", flush=True)

a = np.asarray(src.convert("RGB"), dtype=np.float32); g = a.mean(axis=2)
print(f"{'source':28s} mean {g.mean():6.1f}  contrast {g.std():5.1f}  "
      f"p1-p99 {np.percentile(g,1):5.1f}-{np.percentile(g,99):5.1f}", flush=True)

for device, dtype, label in (("mps", torch.bfloat16, "mps bf16"),
                             ("mps", torch.float32,  "mps fp32"),
                             ("cpu", torch.float32,  "cpu fp32")):
    vae = AutoencoderKLQwenImage21.from_pretrained(
        "Qwen/Qwen-Image-2.1", subfolder="vae", torch_dtype=dtype).to(device)
    proc = VaeImageProcessor(vae_scale_factor=16, vae_latent_channels=vae.config.z_dim)
    px = proc.preprocess(src, width=1024, height=1024).unsqueeze(2).to(device, dtype)
    with torch.no_grad():
        lat = vae.encode(px).latent_dist.mode()
        out = vae.decode(lat, return_dict=False)[0][:, :, 0]
    img = proc.postprocess(out.float(), output_type="pil")[0]
    img.save(SRC.with_name(f"vae_rt_{label.replace(' ', '_')}.png"))
    score(img, label)
    del vae, px, lat, out
    if device == "mps":
        torch.mps.empty_cache()
