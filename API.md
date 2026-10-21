# Studio API

The API and page use the same controllers, model checks, download policy, and shared model memory.
Qwen remains at full precision. Selecting a model does not load its weights.

## Discover controls

Read `GET /api/v1/studio` before a run. It describes the selected image, video, and Voice models.
Each capability record declares its supported modes and controls.
These can include sizes, limits, Looks, templates, and effects.
The rendered API reference is at `/api/docs`, with endpoint search and request examples.
The complete OpenAPI document remains at `/api/v1/openapi.json`.
The rendered view loads a pinned Swagger UI asset from a CDN.

| Action | Route |
|---|---|
| Read shared status and recent operations | `GET /api/v1/state` |
| Start an asynchronous operation | `POST /api/v1/operations` |
| Read one operation | `GET /api/v1/operations/{id}` |
| Read its output | `GET /api/v1/operations/{id}/result` |
| Cancel that operation | `POST /api/v1/operations/{id}/cancel` |
| Select an image model | `POST /api/v1/images/backend` with `{"backend":"qwen21_turbo"}` |
| Select a video model | `POST /api/v1/videos/backend` with `{"backend":"ltx25_mlx"}` |
| Release model memory | `POST /api/v1/memory/release` |
| Read rewrite progress | `GET /api/v1/rewrite/state` |

Existing synchronous generate, edit, rewrite, progress, and cancel routes remain available.
A synchronous image request returns JSON with base64 PNG images. A video request returns MP4 bytes.
A video stub returns JSON metadata instead of an encoded file.

## Start and observe work

```sh
curl -sS http://localhost:8765/api/v1/operations \
  -H 'Content-Type: application/json' \
  -d '{"kind":"video","backend":"ltx25_mlx","prompt":"A red sailboat crosses calm water. Fixed camera.","width":384,"height":384,"num_frames":121,"frame_rate":24,"seed":7,"enhance":true}'
```

The response uses status `202` and names the operation with `id`.
Use that ID in the status, result, and cancel routes.
Image operations use `kind: "image"`. Prompt rewrites use `kind: "rewrite"` and `workspace: "image"` or `"video"`.

| Operation status | Meaning |
|---|---|
| `running` | The server prepares the model or runs it. |
| `stopping` | The server has accepted cancellation and waits for the engine to stop. |
| `succeeded` | The complete output is ready. |
| `failed` | The operation failed. Read `error`. |
| `cancelled` | Cancellation ended the operation. Partial images can remain available. |

Wait for `succeeded` before treating a video as complete.
The sampler can reach its last step while decoding and saving continue.
The page shows at most 99% during this interval.

Only one operation runs at a time. A conflicting request returns `409`; the server has no queue.
A stale cancellation also returns `409` and cannot stop a newer operation.
A missing model follows the page's policy: download when configured, otherwise fail with the same reason.
An accepted asynchronous request can fail later. Read its terminal status and error.

## Prompt aids and reference inputs

Send `looks` as a mapping from each offered row name to one option label.
The API appends the corresponding text after the prompt. Image Looks also apply their declared avoid text.

Send `template` as an offered template name.
Send `template_values` as a mapping from bracket names to replacement text.
For example, `[subject]` uses `{"subject":"a blue teapot"}`.
Unknown options and missing replacements fail explicitly.

An image edit accepts `references` as base64 strings or objects with `png_base64`.
Data URLs also work. With `each_reference: true`, `per_reference_prompts` accepts one instruction per reference.
The master prompt leads each instruction. Looks come last.
API `count` names the total output count. Repeat reference instructions in order when that count exceeds the reference count.
A region edit appends the prepared mask as the final reference and sets `mask: true`.
Use the same numbered-image references in the prompt that the model capabilities support.

A video accepts image keyframes, an audio track, or an effect clip as declared by its mode.
Keyframes use `references: [{"name":"first.png","image":"<base64>","frame_index":0,"strength":1}]`.
Audio uses `audio: {"name":"voice.wav","data":"<base64>"}`.
An effect edit uses `kind: "video"`, `mode: "edit"`, `adapter`, `adapter_strength`, and `clip`.
The clip uses `{"name":"source.mp4","data":"<base64>"}`.
Read available adapter IDs and geometry from the selected video capabilities.

Browser tools prepare media inputs: region masks, trimmed clips, and captured frames.
The API accepts those prepared inputs. Theme and Keep preferences remain in the browser.

## Tabs and retained results

Every open tab reads shared server status from startup.
Tabs show API operations, matching cancellation, failures, and completed results.
An API rewrite appears separately until you choose Use prompt, so it does not replace an unfinished draft.
Model selection also reaches other tabs without replacing their prompt text.

Browser results enter tabs within the same browser library. API results are available across libraries.
All libraries observe the shared operation status.
Removing a browser result suppresses automatic reimport without deleting the retained server result.
Clear all also suppresses completed historical results. Outputs that complete afterward remain available.
Each image includes `completed_at`, the Unix time when that image completed.
Native video responses include the same completion time in `X-Studio-Completed`.
The browser uses completion times to reject old results whose responses arrive after Clear all.

Results remain in server memory for up to one hour after completion.
Retention also has limits of 32 operations and 256 MiB, including metadata.
Older results can expire sooner when either limit fills. Missing results return `404`.
A server restart clears operation history. The existing Keep setting controls browser storage independently.

A browser image batch keeps one operation across its continuation requests.
If its tab closes between images, the operation cancels after a 30-second continuation timeout.
Completed images remain available. An asynchronous API batch runs entirely on the server.

## Choose a useful request

The rendered reference offers named examples in each request editor.
Select an example before you press **Try it out**.
Schema placeholders such as `string` do not describe a useful prompt.

For image or video templates, send the template name and its named values.
Do not copy the template text into `prompt`.
Use the exact field names, including capitalization.
This request uses the measured camera template:

```json
{
  "kind": "video",
  "backend": "ltx25_mlx",
  "template": "Slow push-in",
  "template_values": {
    "Subject": "A blue ceramic teapot",
    "surface": "a wooden table",
    "Foreground object": "A red cup",
    "background object": "a green plant",
    "subject name": "the teapot",
    "light": "Soft daylight enters through a window",
    "sound": "quiet room tone"
  },
  "width": 384,
  "height": 384,
  "num_frames": 121,
  "frame_rate": 24,
  "seed": 7,
  "enhance": true
}
```

For a video effect, read the adapter record before you build the request.
Its prompt, strength, geometry, and frame count form one recipe.
A deblur trigger cannot replace a scene instruction for another effect.
Use the named `deblur` or `day_to_night` example as a starting point.

## Encode actual media

Angle-bracket values in examples require replacement. They are not valid encoded media.
The small PNG in image examples tests transport. It does not provide a useful scene.
Image references accept data URLs. Video keyframes, video clips, audio tracks, and Voice references require bare base64.

Use Python to encode file bytes without shell line wrapping:

```python
import base64
import json
from pathlib import Path

reference = base64.b64encode(Path("speaker.wav").read_bytes()).decode("ascii")
request = {
    "kind": "voice",
    "backend": "auk",
    "mode": "clone",
    "text": "Please bring my blue bag to the front desk.",
    "reference": {"name": "speaker.wav", "wav_base64": reference},
    "seconds": 0,
    "convert": "off",
    "seed": 7,
}
Path("request.json").write_text(json.dumps(request))
```

Submit the generated file:

```sh
curl -sS http://localhost:8765/api/v1/operations \
  -H 'Content-Type: application/json' \
  --data-binary @request.json
```

Use the same encoding step for a video keyframe's `image` or a clip's `data`.
A Voice reference must contain WAV bytes. Renaming an MP3 file does not convert it.

## Voice jobs

Read `GET /api/v1/voice/capabilities` for the active Voice model modes, settings, and templates.
Its `loading` record names the weight repository, pinned revision, and first-use download policy.
The model loads lazily. Missing cached weights download on the first Voice operation.
A synchronous `POST /api/v1/voice/generate` returns WAV bytes.
An asynchronous request uses `kind: "voice"` and the same fields.
Clone and edit require one WAV reference. Design requires `voice`.
References must stay within the published duration and byte limits.

Describe a designed voice in detail:

```json
{
  "kind": "voice",
  "backend": "auk",
  "mode": "design",
  "text": "The next train leaves from platform three. Please keep your ticket ready.",
  "voice": "A woman in her thirties reads a public announcement. Her voice sounds calm, clear, and warm. She speaks at a steady pace and medium volume, with a neutral American accent.",
  "seconds": 0,
  "convert": "off",
  "seed": 7
}
```

A short voice description can become spoken content. Use age, tone, pace, volume, and accent.
`seconds: 0` chooses duration from the text for clone or design.
For edit, zero keeps the reference duration. Structured templates can apply their declared duration rule.
`convert: "tw2s"` converts Traditional Chinese characters before synthesis. It preserves Taiwan vocabulary.
Use `"off"` when the source text must stay unchanged.

Voice Design offers six templates: Voice profile, Conversation, Narration, Commanding delivery, Dramatic character, and Emotional delivery.
Each template supplies four editable voice attributes. Omitted attributes use the declared defaults.
Explicit blank attributes fail validation. The spoken `text` remains separate.
A custom Design request supplies `voice` instead of a template. There is no default voice description.
Multiple sentences in one `text` form one continuous clip. Explicit `items` produce separate clips.

```json
{
  "backend": "auk",
  "mode": "design",
  "template": "Narration",
  "template_values": {
    "speaker": "documentary narrator",
    "subject": "an everyday discovery",
    "pace": "measured, unhurried",
    "tone": "warm and thoughtful"
  },
  "text": "The river flows past the quiet village. The first light reaches the bridge.",
  "seconds": 4,
  "convert": "off",
  "seed": 7
}
```

For a batch, set `kind: "voice"` and place each script and template in `items`.
Shared settings apply to each item. Each item can override its template and attribute values.

```json
{
  "kind": "voice",
  "backend": "auk",
  "mode": "design",
  "seconds": 4,
  "convert": "off",
  "seed": 7,
  "items": [
    {"text": "The river flows past the village.", "template": "Narration"},
    {
      "text": "I am glad you made it home.",
      "template": "Conversation",
      "template_values": {"emotion": "warmth and gentle concern"}
    }
  ]
}
```

Designs can produce different speakers. Clone one saved WAV when the script needs a consistent speaker.

The Design structures adapt the [official cookbook](https://github.com/Tencent-Hunyuan/AuK/blob/9481474f107ee4d8dec959b3aed05b0627cebbf8/docs/COOKBOOK.md#12-instruct-tts)
and [official demo descriptions](https://github.com/Tencent-Hunyuan/AuK/blob/9481474f107ee4d8dec959b3aed05b0627cebbf8/src/auk/infer/infer_gradio.py#L25).
These sources describe the structures. They do not prove this application's output quality.

Voice edit templates use `{field}` placeholders and declare their fields separately.
Send the exact template name and its values. The server compiles the instruction.
The Speed template divides the decoded reference duration by its speed value when `seconds` is zero or absent.
An explicit positive `seconds` value overrides that rule.

```json
{
  "backend": "auk",
  "mode": "edit",
  "template": "Speed",
  "template_values": {"speed": "1.5"},
  "reference": {"name": "speaker.wav", "wav_base64": "<replace with base64 of your WAV>"},
  "seconds": 0,
  "convert": "off"
}
```

Use the declared field names, types, choices, and limits.
Offered defaults apply to omitted numeric and choice fields. Supply required text fields.
Unknown names, unknown fields, and invalid values return `400`.
Raw `text` stays available. Raw speed instructions need explicit `seconds` to change the output duration.
For example, the Enhance template compiles this instruction:

```text
Preserve all speakers, remove noise and reverberation, and output clean speech of the same length.
```

The Voice page generates one continuous clip by default.
The UI generates one continuous clip. Use explicit API items for independent clips.
Each batch press submits the next 16 pending sentences, or the remaining count when smaller.
The next press reuses the first designed voice for the same description and character conversion.
The public API still accepts at most 16 items per operation.

## An agent's request procedure

1. Read the current model capabilities and shared status.
2. Choose the exact backend and mode that support the requested inputs.
3. Check parameter limits, reference limits, frame grids, and offered prompt aids.
4. Use an offered template when it matches the requested scene or camera move.
5. For effects, use the adapter's recipe instead of a generic edit prompt.
6. Encode actual media bytes and replace every media placeholder.
7. Submit one asynchronous operation and save its returned status URL.
8. Poll that URL until the status becomes terminal.
9. Fetch retained outputs, including completed partial outputs after failure or cancellation.
10. Save the outputs before retention expires.

A busy response does not create a queued operation. Wait for the active operation to finish before retrying.
Never interpret an engine's 100% sampler progress as a completed operation.

## Ordered batches

Send `items` to run distinct jobs under one operation.
The batch uses one backend and one media kind: `image`, `video`, or `voice`.
Top-level fields supply defaults. Each item can override its prompt, seed, settings, or media.
Each item produces one output. Set `count` to one and keep `each_reference` false.
A batch accepts 1 to 16 items and runs them in order.

For image variations of one prompt, the existing `count` field remains simpler.
For distinct scenes, use the named `image_storyboard` or `video_shots` examples.

This Voice batch shares one reference across two segments.
Replace the placeholder with actual WAV bytes:

```json
{
  "kind": "voice",
  "backend": "auk",
  "mode": "clone",
  "reference": {
    "name": "narrator.wav",
    "wav_base64": "<replace with base64 of your WAV>"
  },
  "seconds": 0,
  "convert": "off",
  "seed": 7,
  "items": [
    {"text": "First, place the blue cup on the table."},
    {"text": "Next, pour the tea slowly and serve.", "seed": 8}
  ]
}
```

For a new narrator, use a detailed shared `voice` description and `mode: "design"`.
The batch designs each distinct voice description and character conversion setting once.
Later design segments with matching settings clone that voice.
This keeps the speaker consistent across the batch.
For later operations, save the first WAV and supply it as a clone reference.

Read `batch_index` and `batch_total` from shared operation status.
The retained result is a manifest with `items`, `completed`, and `batch_total`.
You can read that manifest while the batch runs. Fetch each available item without waiting for later items.
A running single job still returns `409` from its result route.
Each completed item names its own `result_url`. Item indices start at one.
Its `prompt` contains the text sent to the engine after template and Look composition.
For Voice, this is the validated requested text or compiled edit instruction. It is never a transcript.
Its `settings` preserve the requested fields, including the original template and Look selections.
An item result returns image JSON, MP4, or WAV according to its kind.
Fetch completed items after cancellation or failure. A later failure does not discard earlier outputs.

## Inspect another model

The backend lists in `/api/v1/studio` name available model IDs.
Read an inactive model's capabilities without changing shared selection:

```text
GET /api/v1/images/backends/{id}
GET /api/v1/videos/backends/{id}
```

These routes do not load weights or switch the active model.
Use them to compare supported modes, prompt aids, effect recipes, and parameter limits.
Then submit the chosen `backend` in the generation request.

## Cut an audio selection

`POST /api/v1/audio/trim` cuts a WAV recording without a model or generation operation.
It also runs while the studio generates another result.

```json
{
  "audio": {"name": "speaker.wav", "data": "<bare base64 of your WAV>"},
  "start_seconds": 0.25,
  "end_seconds": 1.25
}
```

The response is `audio/wav`. It preserves the sample rate, channel count, sample width, and selected PCM bytes.
`X-Studio-Duration` gives the exact output duration after sample rounding.
The rendered reference includes a complete named example with real WAV bytes.

Inputs must use uncompressed PCM with 1 to 4 bytes per sample.
The limits are 32 MiB decoded and 120 seconds.
Both bounds must be finite numbers within the source duration.
The end must follow the start. The selection must include at least one sample frame.
The server uses `round(seconds * sample_rate)` for each boundary.
Invalid requests return status `400` with the existing JSON error shape.

## Select a Voice model

Voice offers `drama3` (Drama-3, the default), `auk_base` (AuK), and `auk` (AuK Flash).
Flash uses 4 steps. AuK uses 32 steps and the upstream guidance setting.
The two AuK variants share their modes and templates. Drama-3 declares Generate and Clone; all three support ordered batches.

```json
{"backend": "auk_base"}
```

Send that payload to `POST /api/v1/voice/backend`.
Selection releases the previous model but loads no weights.
`GET /api/v1/voice/backends/auk_base` reads capabilities without selecting or loading it.
Shared state reports the selected model across tabs.

A generation request can set `"backend": "auk_base"` directly.
The server selects that model before the run, and each result records the actual model.
One batch uses one model. A request cannot switch models between its items.
A model switch returns `409` while an operation is active.
The first AuK run downloads about 1.75 GB beyond the shared Flash files, if those files are cached.


## Drama-3 speech

Read `GET /api/v1/voice/backends/drama3` without loading the model. Its default mode is `generate`; AuK defaults to `design`. Omitting backend uses the active Voice model. Send an explicit backend for a reproducible request.

```json
{
  "kind": "voice",
  "backend": "drama3",
  "mode": "generate",
  "text": "[whispers] Keep your voice down. Someone is listening.",
  "temperature": 0.7,
  "top_p": 0.7,
  "top_k": 30,
  "max_tokens": 1024,
  "seed": 7
}
```

Use `POST /api/v1/operations` for asynchronous work, or `POST /api/v1/voice/generate` without `kind` for a synchronous WAV response. Drama-3 returns 44.1 kHz audio and chooses duration from the script. Its Templates target `text`, not `voice`. The selected engine does not expose Design, Edit, a target duration, or a generation-speed option.

Clone adds `"mode": "clone"`, `reference: {"wav_base64": "<actual WAV bytes>"}`, and `ref_text` containing the exact spoken reference words. References must be at most 15 seconds and 32 MiB. The adapter resamples API WAV inputs to native rate. A trimmed reference needs a corrected transcript. New scripts never become implicit references for later batch items.

A batch supplies `items: [{"text": "First line."}, {"text": "Second line."}]` under shared `kind`, `backend`, and optional reference/sampling settings. Up to 16 independent clips run in order with resident weights and cached reference conditioning. This preserves the same warm-engine advantage as consecutive single API calls; it is not parallel tensor batching.

Progress has an unknown total while Drama-3 generates. Do not derive completion from `max_tokens`: it is a safety cap per internal text chunk, and reaching it fails the operation. The server also rejects an entirely missing audio chunk. Short English synthesis, inline cues and cloning passed the initial checks. Unconditioned Chinese and a longer repeated English script hit the cap; treat them as measured limitations rather than guaranteed capabilities.

Drama-3 internally splits long scripts into 180-byte chunks and joins them into one continuous WAV. This is independent of the explicit API batch items and does not create extra gallery entries.

Drama-3 is the default Voice model and uses the pinned eight-bit MLX checkpoint. The UI automatically keeps the first 15 seconds of longer Clone references, including gallery selections and references carried over from AuK. Trimming clears a copied full-recording transcript: enter the exact words in the retained excerpt. API callers use `/api/v1/audio/trim` before submitting a reference longer than the model limit. Script and prompt fields expand while focused.

LTX Generate always applies the pipeline's Gemma-3 prompt enhancer before video encoding, for both LTX-2.3 and LTX-2.5 and for audio-conditioned generation. LTX-2.5 still uses its Gemma-4 tower for text encoding. The compatibility `enhance` request field cannot disable this pass. The separate Rewrite endpoint/button remains available to edit the prompt beforehand. Edit adapters retain their supplied prompt unchanged. Eligible Generate batches enhance their prompts in one model load, release the enhancement process, then render. Auto retains per-item generation for measured regressions, including the enhanced LTX-2.5 two-item 1920×1088, 17-frame, 24-fps text case. Eligible LTX-2.5 text batches reuse the video pipeline within its measured geometry/memory limits. Other Generate batches render clips sequentially after shared enhancement. Mixed Edit batches retain per-item execution. One operation reserves the engine throughout both phases; enhancement is preparation, not a completed result.

Each endpoint description now explains when to choose it, required discovery, how to use its output, and recovery choices. Start with `/api/v1/studio`, inspect a candidate's capabilities without switching models, then submit an operation and poll its status URL. Named template and adapter recipes are preferred when they match the task.
