# The MPS VAE encode defect

Status: worked around in `qwen21_edit.py`, root cause not yet proven, nothing
filed upstream.

## Symptom

Every image that passes through the Qwen-Image-2.1 VAE *encoder* on MPS comes
back with its contrast crushed. Blacks and whites both disappear and the whole
frame lands in a narrow mid-grey band. The instruction following is unaffected,
so an edit does the right thing and then renders it badly.

Text-to-image never shows this, because that path only *decodes*.

## Environment

| Item | Value |
|---|---|
| Machine | Apple M5 Pro |
| macOS | 26.6.2, build 25G83 |
| torch | 2.14.0 |
| diffusers | git 9f1246971270c84dcbe71233edb7a519596a5d02 |
| Env | `PYTORCH_ENABLE_MPS_FALLBACK=1` |

The macOS build matters. See "The OS lead" below.

## Evidence

`vae_device_sweep.py` in this directory runs one image through
`vae.encode` then `vae.decode`, with no transformer and no pipeline. It sets
the VAE dtype and the input dtype together, so dtype is genuinely controlled.

```
source                       mean  147.6  contrast  64.2  p1-p99   4.7-230.3
mps bf16                     mean  100.4  contrast  17.8  p1-p99  53.0-144.7
mps fp32                     mean  100.5  contrast  17.8  p1-p99  53.0-144.7
cpu fp32                     mean  147.8  contrast  64.2  p1-p99   5.3-230.3
```

Two things to read off this table:

1. CPU reproduces the source almost exactly. The VAE round trip is near
   lossless, so the weights and the call are correct.
2. bf16 and fp32 on MPS give the *same* wrong answer, 17.8 against 17.8. A
   precision problem would drift apart at two precisions. An identical wrong
   result points at a wrong code path, not at rounding.

A full edit, before and after the workaround, same prompt and same seed 505:

```
source     cjk_bf16.png         mean 152.1  contrast 63.7  p1-p99  4-232
broken     edit_sign.png        mean 106.3  contrast 18.3  p1-p99 59-150
fixed      edit_sign_fixed.png  mean 155.0  contrast 62.0  p1-p99  6-232
```

## Ruled out

Each one tested as a single variable:

- The prompt. A null edit ("change nothing") degrades identically.
- The KV cache. `--no-kv-cache` gives identical output and runs 2.4x slower,
  438s against 186s.
- Premultiplied alpha. Alpha is 1.0 almost everywhere, and un-premultiplying
  changes nothing.
- The arguments. The call matches the official diffusers example.
- The engine and the hardware. Text-to-image through the same pipeline on the
  same machine is clean: mean 164.6, contrast 63.0.
- VAE encode precision. fp32 is identical to bf16, as the table above shows.
- Latent normalization channel mismatch. Encode and decode both resolve to
  `z_dim`.
- Temporal and causal-conv padding. `QwenImage21CausalConv3d` squeezes the
  temporal dimension on purpose.

A high-pass measure *rises* under the defect, 19.6 to 39.4. That is added
weave-like noise, not recovered detail.

## The workaround

`qwen21_edit.py` wraps `_encode_vae_image` and runs that one call on CPU in
fp32. Everything else stays on MPS. It is the default. `--vae-encode-on-mps`
restores the broken path for retesting.

Encode runs once per reference image, so the cost is about 16s on a 1024 edit,
202s against 186s. Peak memory does not change at 45.6 GiB.

## The OS lead

This is the most important open thread, and it was found late.

pytorch/pytorch#197114, "[MPS] Conv3d returns incorrect results in contiguous
(NCDHW) memory format", is nearly this symptom. It resolved without a code
change. The reporter updated macOS from 26.2 (25C56) to 26.7 (25G229) and the
wrong results disappeared. A PyTorch collaborator could not reproduce it on
M5 Pro, M3 Ultra, or M2. The thread concluded that Apple's MPS framework was
broken in that OS build, not PyTorch. A maintainer then asked whether PyTorch
should route old OS versions to different kernels.

This machine runs macOS 26.6.2, build 25G83. That is **below** the 26.7
(25G229) that fixed #197114.

So the defect here may be the same Apple framework bug, already fixed in an OS
release that is not installed.

## Upstream search, as of 2026-09-21

pytorch/pytorch, nothing matching this case. Related and informative:

| Issue | State | Title |
|---|---|---|
| 197114 | closed | [MPS] Conv3d returns incorrect results in contiguous (NCDHW) memory format |
| 188335 | closed | [MPS] Grouped/depthwise Conv2d gives incorrect results for batch_size > 1 (fp32 only) |
| 100334 | open | MPS device inference all same value |

PyTorch carries a `module: correctness (silent)` label, so wrong numbers on MPS
are a recognised category.

huggingface/diffusers, nothing. No MPS VAE encode report and no
`prepare_latents` dtype report. Issue 14821 is open against Qwen-Image-2.1 but
covers `torch.compile` incompatibility, which is unrelated.

## Confidence

- **MPS returns different and much worse numbers than CPU for this VAE encoder
  on this machine.** High. Device was the only variable, the gap is far beyond
  float tolerance, and both dtypes fail identically.
- **The fix belongs in PyTorch.** Low. The precedent above says this symptom
  class has already resolved once as an Apple OS bug.
- **The `prepare_latents` dtype asymmetry is a diffusers bug.** Moderate. The
  inconsistency is real and readable in the source. A maintainer can fairly
  answer that the pipeline assumes `vae.dtype` equals the pipeline dtype.

One loose end is mine: `PYTORCH_ENABLE_MPS_FALLBACK=1` is set, including inside
the probe. It should be numerically transparent. That is untested.

## Next steps, cheapest first

1. **Update macOS past 26.7 (25G229) and rerun `vae_device_sweep.py`.** If the
   defect vanishes, there is nothing to upstream and the workaround becomes an
   OS-version guard.
2. **Unset `PYTORCH_ENABLE_MPS_FALLBACK` and rerun the encode.** If it raises,
   the error names the offending op for free.
3. **Repeat on a synthetic input and two more images.** One image and one run is
   thin evidence for a bug report.
4. **Bisect the layer stack.** Hook every submodule of the VAE encoder, run the
   same input on cpu and mps, record the max absolute difference per module
   output. The first module where the difference jumps from ~1e-6 to large is
   the culprit.
5. **Test contiguity at that call site.** `QwenImage21CausalConv3d` subclasses
   `nn.Conv2d` and squeezes the temporal dimension, so tensors reach the kernel
   through reshapes. If a `.contiguous()` fixes it, the CPU detour and its 16s
   can go, and the bug report gets much sharper.

Do not file anything upstream until step 1 is done.

## The second bug, separate from all of the above

`QwenImage21Pipeline.prepare_latents` casts the input image to the *pipeline*
dtype. The decode path casts to `self.vae.dtype`. Two casts, two sources of
truth, in one class. So `pipe.vae.to(torch.float32)` on its own raises:

```
RuntimeError: Input type (c10::BFloat16) and bias type (float) should be the same
```

This is small, self-contained, and independent of the MPS question. It is the
one piece here that is ready to send as a diffusers PR.
