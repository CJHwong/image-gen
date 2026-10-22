# Porting the engine off Apple Silicon

Status: the probe recognizes MLX GPU devices. macOS is the only platform this
repo has run on. The seam is `studio/l4_frameworks_and_drivers/engines.py`.

## What decides today

`engines.py` probes for MLX and `create_studio` refuses a real studio without
it. That refusal is not a platform check: it asks whether a capability is there.
The stub passes the refusal, so the page stays workable on a machine that cannot
run a model at all. The refusal happens before the port is bound, so such a host
never occupies it.

The probe reads `mx.is_available(mx.Device(mx.DeviceType.gpu))`. This checks a
GPU without naming Metal or CUDA. The pinned mflux release declares an MLX CUDA
build for Linux, but this repo has not tested its model paths on CUDA.

**There is one startup gate now, not two.** Instruction editing used to run on a
diffusers pipeline in a child process, and a non-Apple host was blocked from it
separately by that script's MPS device check. mflux 0.21.0 ported the Qwen3-VL
vision tower, so editing runs on the same MLX engine as generation and the child
is gone. Both models behind qwen21 and the one behind flux2 are now mflux models.
The MLX GPU probe is the startup gate. Real CUDA generation and editing remain
unverified.

## Why a Mac cannot test this

The branch that needs proving is the non-Apple one. Any Apple machine exercises
the macOS path, which is the path that already works.

A second Mac is still worth running: it catches hardcoded assumptions from the
development machine and gives a second chip. It is not portability proof.

## The decisions a non-Apple build forces

| Decision | Today | Why it changes |
|---|---|---|
| The engine | MLX only, and a host without an MLX GPU is refused | The pinned mflux release declares an MLX CUDA build for Linux. This repo still needs a real CUDA run for generation and editing. |
| The memory guard | The two qwen21 models are freed against each other, sized for a 64 GB machine | That is a VRAM fact, not a platform fact. `mx.device_info()` reports `max_recommended_working_set_size` (26800603136 bytes on the M1 Pro here, measured 2026-09-25); CUDA has `torch.cuda.mem_get_info()`. A large card could hold both. |
| The quantization | mflux quantizes the transformer and the VAE, and the badge the page shows follows it | Another engine quantizes another way, and the badge has to follow that engine. |
| The weight layout | mflux reads its own layout and downloads `Qwen/Qwen-Image-2.1` itself | Another engine wants another layout. flux2 already takes a hand-placed folder, so the pattern exists. |

## Numbers already measured, all on Apple Silicon

| Fact | Value | Source |
|---|---|---|
| mflux generate peak | 30.68 GB | `generator.py` `build_model` |
| Peak without the memory saver | 45.01 GB | same |
| Text encoder, resident | 17.5 GB | mflux qwen21 README |
| Weights on disk | about 33 GB bf16 | README |
| Model rebuild after a release | 3.8s | `qwen21_backend_gateway.py` |
| Generate, seconds per step at 1.05 MP | 5.76 | `capabilities.py` |

The edit constants in `capabilities.py` were fitted against the removed diffusers
path and were re-measured against the in-process engine when it landed. Read the
comment beside them for the numbers and the machine.

## Upstream, checked 2026-10-05

| Pull request | State | What it does |
|---|---|---|
| mflux #736 | merged 2026-09-21 | txt2img, img2img, quantization. This was the pin. |
| mflux #741 | merged 2026-09-27 | Reference editing, RGBA output and prefix caching. |
| mflux #749 | merged 2026-10-01 | Instruction edit with prefix KV cache. It removed the diffusers child on macOS, which is what this repo then did. |
| mflux #764 | merged 2026-10-01 | The `viggle_turbo` scheduler. |

The pin is the `v.0.21.0` release. Two things about that release are worth knowing
before a port is built on it:

- The edit variant's `generate_image` takes no `scheduler` argument, so the viggle
  schedule reaches it through `gateways/image/viggle_turbo_schedule.py`. That module is a patch
  with a test that fails the day upstream adds the argument.
- The edit call takes `image_paths`, not images, so the references go to disk for
  the length of a run. `edit.py` records why.

## Next steps, cheapest first

1. **Get a Linux CUDA host.** The current office Mac cannot prove this path.
2. **Run Qwen generation and editing on that host.** If either path fails, pick
   an engine that supports both operations.
3. **Measure a generate and an edit on that host.** Re-fit the constants in
   `capabilities.py` against those runs.

The probe change makes the existing MLX CUDA build reachable. The host tests
remain necessary because this repo has no CUDA generation or edit run.
