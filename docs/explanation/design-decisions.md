# Design decisions and measurements

These notes preserve the workloads, limitations and measured reasons behind Open Imagine’s implementation.
Timings describe the recorded machine and invocation, rather than a guarantee for another configuration.
See the [README](../../README.md#documentation) for an overview.

**Cached Image weights can still page.** A three-image UI control slowed from 46 to 61 to 71 seconds despite keeping the model. At 1104×1472 after Rewrite, a bounded active-residency spike reduced the batch from 199.3 to 169.0 seconds, with all three output images pixel-identical and much less system swap traffic. Qwen Turbo now applies this bounded policy during Generate, Edit, and API batch prompt preparation. It restores the previous wired-memory limit while idle, including after an error or cancellation. The policy changes memory residency, not precision or sampling; its temporary cost is less reclaimable RAM for other applications. Measured gains depend on memory pressure. A later fresh-process production check took 79.2, 62.0, and 69.9 seconds with the same output pixels; it used a different cold-start state, so it is not a matched speedup comparison and does not establish monotonically decreasing item times.

**Drama-3 memory residency.** Under office memory pressure, the original first request took 238 s; an active-generation wired-memory spike took 60 s with the same generated PCM. The engine now temporarily raises its process wired limit, bounded by MLX’s recommendation and 75% of RAM, then restores it while idle. This preserves precision and sampling, at the cost of less reclaimable RAM during generation. Experimental language switching can separately generate long silence; a plain bilingual script worked for the reproduced seed.

- **Application policy stays behind ports.** Batch validation and operation completion live in use cases; the composition root injects the shared operation store. JSON mapping and presentation stay in adapters, and import contracts enforce their independence from concrete model and storage gateways. The workspace guide is shared across Image, Video and Voice.
- **One page, one adapter per model.** The page asks the model what it supports and hides the rest. A new model is one adapter in `studio/`, and the page does not change. [studio/ARCHITECTURE.md](../../studio/ARCHITECTURE.md) has the layers and how to add a model.
- **One engine for qwen21.** Generate and instruction edit both run through mflux on MLX. Editing needs the Qwen3-VL vision tower, which mflux ported in 0.21.0; before that it ran on a diffusers pipeline in a child process, which held 38.7 GiB on MPS and had to free the mflux model before every edit.
- **Viggle Turbo runs six steps and no more, after spiking its nine-step mode.** Its card offers a second mode: seven steps on the adapter, then the adapter off and two steps on the base model, on a wider sigma table. Both halves are reachable from here, mflux's scheduler registry takes a nine-node table by name and a runtime adapter switches off when each layer's scale is set to zero, and both were proved working on real weights. It still does not win. On one scene and one seed, nine steps scored 21.1x containment against six's 21.2x, so it buys nothing where six steps is weak, and it took 38.2s against 27.3s. The only visible change was on a plain generate, where nine steps kept more glaze detail and added background grain. A spike that does not win is still worth the run: it is the difference between a mode that was measured and one that was assumed.
- **Image batches keep one engine and produce images in order.** A batched flux2 tensor call measured 2 to 8% slower per image and used more memory.
  The studio keeps sequential outputs under one reservation and publishes each completed image.
  The Image count control uses the same prepared batch use case as explicit API items, including per-reference edits.
  The count menu also respects the API limit of 16 total items when editing references separately.
  Backend preparation can share measured setup work without changing output order; a batch does not imply parallel denoising.
  Official Qwen Turbo generation batches encode distinct prompts before the first sampler frees the text encoder.
  A controlled three-image test at 768 x 768 and eight steps took 62.62 seconds against 84.83 seconds sequentially.
  Model builds fell from three to one, and all PNG files matched byte for byte.
  Its Metal peaks were 30.100 GB with preparation and 30.095 GB without it.
  The product API comparison took 66.77 seconds for the batch against 97.84 seconds for matched single requests.
  That product comparison includes a 45.4-second single request under host memory activity; the others took about 26 seconds.
  The controlled comparison shows a 26.2% reduction for those three prompts. These figures do not promise a universal ratio.
  Earlier image URLs remained readable while later images ran.
- **Fast mode is optional and belongs to one video request.** LTX-2.5 offers it under Advanced,
  and API clients send `fast_mode: true`. It uses float16 transformer computation with the same q8 weights.
  Details and motion can differ, even with the same seed; speed varies by geometry and input.
  Default computation stays on when the option is off, even if the server inherits a precision environment variable.
  Each child receives its own setting, so switching requires no restart and never mutates the server environment.
  Every item in a batch must share the setting. The UI shows the active operation's choice, locks the control,
  restores an observer's own choice afterward, and records Fast mode in result metadata.
  Image-conditioned, audio-conditioned, and Upscale 2× Edit API checks all completed in both modes.
- **Video progress adds both stages.** The runner combines the engine counters into one total.
  The page holds at most 99% until decoding and saving finish.
  A completed sampler does not claim that the result is ready.
- **LTX-2.5 batches choose an execution profile by geometry, length, and physical memory.**
  One clip is sampled at a time. The API still accepts up to 16 items; item count does not multiply activation memory.
  Eligible homogeneous text-only batches encode unique prompts once and free Gemma before video work.
  On machines with at least 64 GiB, the planner stays within the measured 1920×1088×97 pixel-frame budget,
  at most 121 frames, 24 fps, and a 1920-pixel maximum side. A smaller spatial size can therefore support a longer clip.
  It selects stage cleanup with retained weights and a 1 GiB allocator cache, or transformer offload during decoding.
  Eligible Generate batches now enhance all prompts in one Gemma load, exit that process, then encode the enhanced text
  in the video child. This preserves native enhancement while allowing the same calibrated reuse profiles.
  Earlier profile timings were measured without enhancement; current enhanced measurements are reported separately.
  Auto retains the per-item path for the measured enhanced two-clip 1920×1088, 17-frame, 24-fps text case:
  248.35 seconds per-item versus 282.15 with shared enhancement only and 267.10 with offload reuse.
  Every decoded frame matched. The guard applies to that exact workload; other counts and durations are unchanged.
  Two 1920×1088, 49-frame clips took 691.37 seconds with offload versus 707.90 seconds sequentially, a 2.3% reduction.
  Peak Metal allocation was 11.6 GiB, versus 31.7 GiB with full residency.
  Two 97-frame clips took 1587.98 seconds with cleanup versus 1608.75 seconds sequentially, a 1.3% reduction;
  the cleanup peak was 37.7 GiB. Corresponding decoded frames matched exactly.
  These are modest gains on one machine, not a guarantee for every shape or a sixteen-item high-resolution timing.
  Low-resolution reuse is disabled after a matched four-item 384×384, 121-frame test regressed from 215.16 to 221.42 seconds.
  Sizes at or below 768×768 remain sequential: two 768×768, 121-frame clips took 394.28 seconds sequentially,
  394.77 seconds resident, and 412.68 seconds with cleanup. Effects, audio, keyframes, mixed geometries,
  other models, unknown memory, and workloads outside the budget also use sequential runs.
  Set `[mlx_video].batch_policy = "sequential"` to disable all cross-clip reuse for a baseline.
  `"enhance_only"` shares enhancement while rendering with fresh pipelines; `"auto"` also selects the calibrated video profile.
  Each validated item start resets the one-hour engine timeout. Initial loading is bounded too, so a valid long batch
  is not killed merely because its combined duration exceeds one hour.
  Larger apparent gains in earlier low/mid experiments did not hold against every fresh control.
- **Full Qwen also prepares varied batch prompts once.** One matched engine pair uses three 768 x 768 images, 20 steps, and guidance 1.
  Preencoding reduces the total from 189.78 to 175.88 seconds, or 7.3%, and model builds from three to one.
  All three PNG files remain byte-identical. The measured Metal peaks stay near 30.75 and 30.76 GB.
  This hook covers all-generate batches. Mixed and edit batches keep their existing sequential path.
  These figures describe the engine pair. The full Qwen factory keeps its existing rebuild path for later new prompts.
  A later real API correctness run reproduces all three baseline PNG files. Its source digests match before and after the run.
- **Turbo restores only its text encoder for a new prompt.** The transformer, VAE, and prompt cache stay resident.
  Other model factories keep their existing rebuild path.
  One matched engine pair of three varied 768 x 768, eight-step jobs measured 114.41 seconds with full rebuilds and 82.78 seconds with encoder restoration.
  The restored path builds the model once instead of three times. All three PNG files remain byte-identical.
  Its measured Metal peak is 30.10 GB against 46.71 GB in the baseline, whose memory grows across rebuilds.
  Each encoder restore takes about one second. These figures describe that engine pair; they do not establish an API-wide ratio.
  A later real API correctness run reproduces all three baseline PNG files. Its source digests match before and after the run.
- **Turbo edits retain bounded reference and instruction encodings.** Each model owns two caches, each capped at eight entries and 64 MiB.
  The prompt key uses the instruction and ordered image pixels, modes, and sizes. The reference key uses the effective numeric tensor.
  The caches evaluate their arrays before retention. Releasing the model releases those arrays.
  One matched engine pair uses a shared 512 x 512 reference, blue/red/blue instructions, eight steps, and seeds 7/7/8.
  It measures 98.53 seconds without the caches and 73.40 seconds with them, with all three PNG files byte-identical.
  The pair records one prompt hit and two reference hits. Retained values use 4.77 MB, and Metal peaks stay near 36.63 GB.
  These figures cover those repeated inputs. New references and instructions still pay their encoding cost.
  Only the official Turbo edit factory enables this path.
  A later real API correctness run reproduces all three baseline PNG files. Its source digests match before and after the run.
- **Voice batches reuse a neutral voice sample inside the AuK adapter.**
  Each description, language, and character conversion gets one sample per batch.
  The sample uses fixed text. Every requested script clones that sample, including the first script.
  A new batch creates new samples. Explicit Clone and Edit requests keep their chosen recording.
  The old shortcut cloned the first finished script. In a 16-item AuK test, four clips repeated that script.
  Two speech recognizers confirmed those four failures. Unique WAV files did not prove correct speech.
  The corrected path retains the loaded engine and its reference cache.
  The corrected 16-item API batch completes in 263.56 seconds on the office M5 Pro.
  The larger speech recognizer matches all 16 scripts. Generate, Edit, and Cancel checks also pass.
  This timing has no matched control, so it does not prove a new speedup.
  Generate creates one continuous clip and clears the submitted inputs after success.
  The public API keeps its limit of 16 items per operation.
- **Voice retakes reuse only the last reference and exact instruction.** The resident child retains one decoded reference and its evaluated audio latent.
  A content hash detects changed recordings, even when a file path stays the same.
  A separate one-entry cache retains evaluated conditioning for the exact instruction and reference bytes.
  A changed instruction or recording replaces that entry. Releasing the child releases both caches.
  Two measured six-take arms cut reference work from about 0.17 to 0.03 seconds and total time by 2.2%.
  With reference reuse already active, two more six-retake arms reduced total time from 5.35/5.26 to 4.61/4.60 seconds.
  That is 13.1% less elapsed time for those repeated-instruction runs, not for new text.
  Every compared WAV remains byte-identical. Each run makes six distinct outputs from six seeds.
  These measurements use warm AuK Flash, one shared reference, and 2.5-second output clips on the office machine.
  Cold model loading and the first instruction still pay their full cost.
  The real backend gate also passes design, clone, edit, progress, and cancellation with both caches enabled.
- **An audio track takes the guided pipeline, and it costs about 2.5 times a plain clip.** Generate enters `a2vid_two_stage` when a track is attached: the full model at half resolution for 30 guided steps, then the distilled refinement. Measured on the office M5 Pro on 2026-10-19, one 384 x 384 clip of 25 frames at seed 7, with the same prompt and reference: 243.4 s with a track against 91.4 s on the distilled path. The reference survives the switch. A frame-0 keyframe of a red disc on green came back at 19.7% red against the reference's 19.8%, in a box within one pixel of it, 96..287 against 96..288. Without the reference the same run made a different scene, 13.9% red in an off-centre blob and almost no green, so the frame is the reference and not the prompt. The track returns unchanged: 440 Hz in, 439.7 Hz out over the clip's 1.042 s. Every track is decoded to stereo PCM before the render, because the audio VAE's first convolution takes two channels and a mono WAV died there with `expected input[1, 1, 107, 66] to have 2 channels`. Only the clip's own seconds are decoded.
- **An edit keeps the scene and changes its light, and the people move differently.** Measured on the office M5 Pro, one daylight clip of 97 frames at 768 x 448, seed 7, through `ltx_pipelines.ic_lora`: the frame darkens from 107.2 to 39.2 mean luminance, the buildings, the street and the crosswalk hold, and the crowd is re-synthesised rather than preserved, so a figure crossing left in the input may cross right in the output. The card says the same thing in its own words, that the reference drives structure and the prompt drives the lighting. Two stages with stage 2 bare is worse than that: the market stall in the input comes back as a parked car, which is what `--stage-2-ic-lora` is for, and every effect's own declaration carries whether it wants it. The single-stage recipe several cards name was measured too, at 1536 x 896 so its half-resolution output lands on 768 x 448, and it did not keep the stall either, so the two-stage path with the conditioning kept is what the form drives.
- **The transformer is built once per clip, not once per stage.** A stage builds its transformer for each denoise pass and frees it when the pass returns, so one clip read the 39.1 GB file twice, 78 GB of the 115 GB a clip loads. The runner's wrapper keeps the first build and hands the same model to the second pass, then frees it when that pass ends, which is the last one: the pipeline runs one denoise pass per stage, its two stages are the two calls in `stream_chunks`, and the decode that wants the room comes after them. The build does not depend on the shape of the latents, because the single GPU builder ignores the video tools the stage hands it, so no shape enters the build; that was checked at the one shape measured here. Measured on the office M5 Pro, one 384 x 384 clip of 73 frames: the second build cost 32.4 s and 36.2 s in two runs, and with the hold the second pass entered its denoising loop in the same millisecond as its build line, against a 32.4 s gap without. Both runs made the same clip: 73 of 73 frames identical and no audio difference. The block streaming path is left alone, because it frees its blocks between passes by design. At the largest shape the form offers, 1280 x 704 at 73 frames, the second build cost 40.0 s without the hold and 0.003 s with it, and the hold's own window, which covers the upsampler, cost 1.3 s there, 1.9 s against 3.2 s. The two runs' totals are not comparable and I do not quote them as a gain: the run with the hold took 499.8 s against 393.2 s, and all of that difference sits in the first stage, whose first step took 131.7 s against 26.7 s. That step swings with the machine rather than with this change, because the plain wrapper measured 20.1 s and 110.3 s at 384 x 384 in the same evening. The release lands before the decode builds its VAE, so the decode cannot see the hold at all.
- **A clip's first denoise step cost 20 s to 110 s in the runs measured, and the machine's memory moved with it.** On the office M5 Pro, one 384 x 384 clip of 73 frames: the first step of the first stage took 20.1 s and 30.5 s in two runs with the machine to itself, and 110.3 s in a run while the studio's own server was up, RAM held 63 GB of page cache, and swap held 7.7 GB of 9 GB. Those runs differ in more than one thing, so this points at the memory without proving it. The steps after the first cost 0.8 s to 4 s. A clip is 11 steps whatever its length, because the distilled schedule is a table: 3 seconds of video and 15 seconds of video run the same steps, and length changes the tokens in each step and not the count. So a 15 second clip costs about twice a 3 second one and not five times, and the wait is the load and the first use rather than the frames.
- **The Turbo checkpoint is sampled on the table it ships.** mflux builds `linspace(1, 1/steps, steps)` plus a zero for this checkpoint and never reads the `sample_sigmas` it carries: the grep for that name over the mflux package finds nothing, and the model card says the opposite, that the table "is loaded automatically" and that `num_inference_steps` alone does not override it. So `gateways/image/shared/qwen21_turbo_schedule.py` registers the checkpoint's own eight nodes as a scheduler, the way mflux registers Viggle's six, and eight nodes means eight steps. Measured 2026-10-16 on the office machine, one prompt and two seeds at 768 x 768: the two tables differ by RMS 26.3 and 35.3, as much as 8 steps differ from 40, and the linear table carries 2.5 to 3.1 more edge energy. Two seeds and one prompt say which way a schedule moves a picture, not which is better; the shipped one is the publisher's own and the one they evaluated. Both were also timed at 8, 20 and 40 steps, which is a flat 1.41 s/step with about 0.6s of fixed cost at 768 x 768, and detail stops improving past 20: edge energy reads 18.28, 19.11 and 19.36 at 8, 20 and 40 steps.
- **One run at a time.** The GPU is full with one run, and two only slow each other. A run from a second tab gets a message to wait, not a place in a queue.
- **One model family in memory.** Image and video workspaces keep separate model choices, but they share one memory slot. The server loads weights only when a run needs them. A workspace switch releases the inactive model. Prompt rewriting uses the same lock and releases its weights when the rewrite ends. Within a run, a model the run uses more than once is held until its last use, and a model it uses once is freed when that use ends. The video transformer is the one held today, and a batch of images holds its engine for the whole batch. A clip builds its video encoder twice as well, 0.59 GB and about a second of the upsampler's 2.4 s, and that one is left alone: sharing it means either copying two blocks' own call bodies, which would drift from the pipeline and could skip the upsample step itself, or caching inside the loader that builds it, which risks handing back the wrong model. Neither is worth 0.7 percent of a clip. The sizes decide what can be held together: on a 64 GB machine the LTX transformer is 39.1 GB and the text encoder it needs beside it is 24.5 GB, which is 63.6 GB of the machine and leaves nothing for macOS and the server, so those two are never resident together and a clip loads them in turn. A workspace switch is what gives the slot back.
- **The server retains results in memory and binds 127.0.0.1.**
  Recent operation metadata and outputs support API clients and all open tabs.
  Results expire after one hour, 32 operations, or 256 MiB, whichever limit comes first.
  A restart clears server history. Temporary media files last only for the run that needs them.
  Browser Keep controls local storage independently. Browser storage belongs to the address and port.
