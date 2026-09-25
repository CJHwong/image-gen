# Porting the engine off Apple Silicon

Status: not started, no host to test on. macOS is the only platform this repo
has ever run on. The seam is `studio/l4_frameworks_and_drivers/engines.py`.

## What decides today

`engines.py` probes for MLX and `create_studio` refuses a real studio without
it. That refusal is not a platform check: a Mac that later wants the diffusers
engine and a Linux box that can only run diffusers both come through the same
probe. The stub passes the refusal, so the page stays workable on a machine
that cannot run a model at all.

The refusal covers generation only. On a non-Apple host an edit is blocked
separately, by the MPS device check in `qwen21_edit.py`, which is decision 1
below. Two blockers, two fixes.

The probe reads `mx.metal.is_available()`. That namespace has no non-deprecated
replacement today: `mx.device_info()` reports the device, its memory and its
limits, but no availability. If a future mlx renames the namespace, the probe
answers no on a capable Mac and the refusal message is the symptom to read.

A diffusers generate engine does not exist. When it does, the builders in
`main.py` pick an engine per backend instead of refusing, and the refusal moves
from `create_studio` into the backend builders.

## Why a Mac cannot test this

The branch that needs proving is the non-Apple one. Any Apple machine
exercises the macOS path, which is the path that already works. Nothing on a
Mac runs the diffusers generate path, because that path is not written.

A second Mac is still worth running: it catches hardcoded assumptions from the
development machine and gives a second chip. It is not portability proof.

## The four decisions a non-Apple build forces

| Decision | Today | Why it changes |
|---|---|---|
| Device selection | `qwen21_edit.py:180` exits when there is no MPS device | Becomes a parameter. `enable_model_cpu_offload` already takes a device. |
| The MPS patches | `PYTORCH_ENABLE_MPS_FALLBACK` at `qwen21_edit.py:75`, and the VAE encode detour to CPU fp32 | Both are MPS workarounds. CUDA needs neither. See `MPS-VAE-ENCODE.md` for the defect the second one avoids. |
| The process shape | The edit engine is a stdio child, because torch and MLX cannot share a process | On CUDA the server process is already torch, so the child pays the pipeline build per edit and buys nothing. A resident pipeline is right there. Two shapes to maintain. |
| The memory guard | Both engines are freed against each other, sized for a 64 GB machine | The two engines must fit in the same memory. That is a VRAM fact, not a platform fact. `mx.device_info()` reports `max_recommended_working_set_size` (26800603136 bytes on the M1 Pro here, measured 2026-09-25); CUDA has `torch.cuda.mem_get_info()`. A large card could hold both. |

## Numbers already measured, all on Apple Silicon

| Fact | Value | Source |
|---|---|---|
| Edit pipeline allocated | 38.7 GiB | `qwen21_backend_gateway.py` class docstring |
| mflux peak | 30.7 GB | same |
| mflux rebuild after an edit | 3.8s | same |
| Pipeline build in the child | 20 to 36s | `edit.py` docstring |
| Two 768 edits down one child | 31.9s then 19.6s | same |
| VAE encode detour, 1024 edit | about 16s (202s against 186s) | `MPS-VAE-ENCODE.md` |

Only the mflux and edit numbers are Apple numbers. The diffusers generate path
has never been timed here, so every estimate for it is unmeasured.

## Upstream, checked 2026-09-25

| Pull request | State | What it does |
|---|---|---|
| mflux #736 | merged 2026-09-21 | txt2img, img2img, quantization. This is the pinned commit. |
| mflux #749 | open, `REVIEW_REQUIRED` | Instruction edit with prefix KV cache. Would remove the diffusers child on macOS. |
| mflux #741 | open | Reference editing, RGBA output and prefix caching. Same ground as 749. |

If 749 or 741 merges, the macOS case collapses to one MLX engine and three of
the four decisions above stop applying to macOS. The non-Apple case is
unaffected either way: MLX does not run there.

## Next steps, cheapest first

1. **Write a live test for qwen21.** There is none. flux2 is the only live test
   in the repo, so a portability break cannot be told apart from a break that
   was already there.
2. **Get a non-Apple host.** NVIDIA or AMD. Nothing below can be proven without
   one, which is why this work is not started.
3. **Make the device a parameter and the two MPS patches conditional.** Then
   measure a generate and an edit on the host.
4. **Test the resident pipeline against the child on that host.** The child
   exists for a reason that does not apply there.

Do not start step 3 until step 2 is done. Writing the code first ships an
unverified path, and this repo's own rule is that a green test is a gate, not
proof.
