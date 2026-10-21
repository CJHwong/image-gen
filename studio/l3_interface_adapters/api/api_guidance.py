"""Task-oriented endpoint guidance: choose a tool, prepare inputs, then use its output."""

GUIDANCE = {
    "readOpenApi": (
        "Read this reference to choose an endpoint and a named request example. Start with readStudio for model IDs, "
        "then inspect only the chosen model's capabilities. Examples with media placeholders need real base64 bytes; "
        "examples name their intended model because settings do not transfer between models."
    ),
    "readStudio": (
        "Start here when asked to make or edit an image, video, or speech clip, or to choose a model. "
        "Read each workspace's backends and active ID; capabilities describe its currently selected model. "
        "To compare another listed model, call readImageBackend, readVideoBackend, or readVoiceBackend without "
        "switching or loading it. Copy mode IDs, parameter values, template names, and adapter IDs exactly."
    ),
    "readState": (
        "Use this to discover work started by another client, recover after reconnecting, or synchronize a UI. "
        "active is the server-wide operation or null; operations contains recent work, including failures and results. "
        "Read the selected model from studio, then poll an individual status_url for your own request. "
        "A busy server has no queue: wait rather than repeatedly submitting work."
    ),
    "readOperation": (
        "Poll the status_url returned by startOperation, for example once per second. Continue while status is "
        "running or stopping; stop on succeeded, failed, or cancelled. Read error on failure and fetch a non-null "
        "result_url, including partial batch results. A progress total of zero is indeterminate; finishing sampler "
        "steps does not mean decoding and saving are finished."
    ),
    "readOperationResult": (
        "Fetch an operation's result_url to retrieve completed media. A single image returns JSON with base64 PNG; "
        "video returns MP4 bytes; speech returns WAV bytes. Explicit batches return a JSON manifest: fetch each "
        "item's result_url separately. Batch manifests can be read during generation and after failure/cancellation. "
        "A pending single result returns 409; missing or expired results return 404. Save bytes locally before expiry."
    ),
    "startOperation": (
        "Prefer this endpoint for generation, editing, rewriting, or an ordered batch: it returns immediately and "
        "keeps work running when the client disconnects. Send kind and the fields of that media request; explicitly "
        "choose backend and mode for reproducible behavior. For varied outputs, add items with shared defaults at "
        "the top level. Save the returned id/status_url, poll until terminal status, then fetch result_url. "
        "202 means accepted, not successful: validation, model loading, and inference may fail in the worker. "
        "Only one operation owns model memory; 409 means busy and nothing was queued. Model loading/download policy "
        "matches the page. Results expire after one hour, 32 operations, or 256 MiB, and on restart. "
        "API batches need no browser continuation; legacy page image batches reserve their next item for 30 seconds."
    ),
    "cancelOperation": (
        "Use the id of your active operation to stop a long render or speech job without cancelling unrelated work. "
        "204 acknowledges the request; continue polling until cancelled or another terminal status. "
        "Completed batch items remain readable through result_url. A finished operation returns 409; an unknown "
        "or expired ID returns 404."
    ),
    "selectImagesBackend": (
        "Use this to change the default image model shown by the UI. Send a backend ID from readStudio; this selects "
        "without loading weights. Prefer an explicit backend on a generation request when only that job needs it. "
        "Re-read capabilities after switching: size, steps, guidance, editing, Looks, and templates can change. "
        "409 means an operation holds the model slot."
    ),
    "selectVideosBackend": (
        "Use this to change the default video model shown by the UI, without loading weights. Send an ID from "
        "readStudio and re-read its capabilities: adapters, sizes, frame counts, audio inputs, and templates vary. "
        "For a single job you can instead send backend directly in that request. Switching while busy returns 409."
    ),
    "selectVoiceBackend": (
        "Use this to change the default Voice model without loading it. Read supported modes after switching: "
        "AuK/AuK Flash offer design, clone, edit; Drama-3 offers generate and clone. AuK clone needs no transcript; "
        "Drama clone needs ref_text matching a WAV reference of at most 15 seconds. "
        "A generation request can select backend directly. Switching while busy returns 409."
    ),
    "releaseModelMemory": (
        "Use this after work when the user wants model memory freed. It releases loaded weights without generating "
        "media or deleting retained results. The next generation reloads its model and may be slower. "
        "Wait for active work to finish or cancel your operation first; a busy server returns 409."
    ),
    "readImageBackend": (
        "Use a listed image backend ID to inspect a candidate model before choosing it. This does not select or load "
        "the model. Read the desired mode's params, min/max references, Looks, and templates. Use edit for changing "
        "existing images and size=match when offered to preserve reference size. Use the discovered IDs/defaults "
        "in startOperation; another model's steps or guidance may be invalid."
    ),
    "readVideoBackend": (
        "Inspect a listed video model without selecting/loading it. For camera moves or dialogue, inspect Generate "
        "templates before writing a freehand prompt; send template plus named template_values. For a visual effect "
        "on an existing clip, inspect adapters and use the chosen adapter's own prompt, strength, width, height, "
        "and num_frames. Choose an exact offered shape and frame grid; do not invent a nearby resolution."
    ),
    "readVoiceBackend": (
        "Inspect a listed speech model before selecting/loading it. Read default_mode, modes, params, templates, "
        "reference_sample_rate, and max_reference_seconds. Use AuK design for a described voice or Drama generate "
        "for script-directed delivery. Use clone to copy a recording's voice; Drama also requires its exact transcript. "
        "Only send parameters declared by that model/mode; template.target tells you whether it fills text or voice."
    ),
    "readVoiceCapabilities": (
        "Read the currently selected Voice model's modes, required inputs, sampling controls, and templates. "
        "Use readVoiceBackend to inspect a different model without changing this selection. "
        "Do not assume every model accepts a voice description, target duration, conversion, or Edit mode."
    ),
    "generateImage": (
        "Use this synchronous endpoint to draw still images and keep the HTTP request open until they finish. "
        "For long work or reconnectable clients prefer startOperation with kind=image and mode=generate. "
        "Choose backend/size/steps from capabilities, and inspect templates and Looks for the requested style. "
        "count repeats one request; items on startOperation makes an explicit varied batch. "
        "Read every returned base64 PNG and its actual seed; the page displays the same shared operation."
    ),
    "editImage": (
        "Use this to modify supplied still images. Send reference PNG/JPEG bytes as base64, an edit instruction, "
        "and a backend supporting Edit. Choose size=match when offered to retain reference geometry. "
        "Multiple references normally condition one output together; each_reference edits them separately and can "
        "use per_reference_prompts. This call waits for completion and returns JSON/base64 PNG. "
        "Prefer startOperation with kind=image and mode=edit for reconnectable execution."
    ),
    "generateVideo": (
        "Use this synchronous endpoint for a clip from text, optional image keyframes, and optional audio. "
        "Prefer startOperation with kind=video and mode=generate for long renders. "
        "Inspect Generate templates for camera moves, composition, dialogue, and sound before constructing a prompt. "
        "Use an exact capabilities shape/frame grid; output duration is num_frames/frame_rate. "
        "The generation pipeline always enhances the prompt before encoding it; this is independent of Rewrite. "
        "Put bare base64 bytes in references/audio, never local paths or example placeholders. "
        "Return media is MP4, not JSON, except on the stub server."
    ),
    "editVideo": (
        "Use this for an existing clip plus an offered effect adapter; use Generate for a new scene/camera move. "
        "Read adapters from the selected backend and copy the chosen effect's recipe, including dimensions and "
        "num_frames; adapters are not interchangeable and some re-synthesize motion. Send the clip as bare base64. "
        "This call waits and returns MP4 bytes. Prefer startOperation with kind=video and mode=edit for long jobs."
    ),
    "rewriteImagePrompt": (
        "Use this to expand a rough image prompt or explain a referenced image before generation. "
        "Send prompt and optional image references; read the returned prompt and optional size suggestion. "
        "Rewriting produces text, not media, and uses the shared model slot. "
        "Inspect templates first when the task already matches one. Use kind=rewrite and workspace=image "
        "on startOperation for asynchronous rewriting; use generateImage/startOperation afterwards to render."
    ),
    "rewriteVideoPrompt": (
        "Use this to expand a rough scene description before rendering a video. Send prompt and optional image "
        "references; use the returned text in a separate Generate request. This does not render media and uses "
        "the shared model slot. Inspect camera/dialogue templates first for a known composition. "
        "Use kind=rewrite and workspace=video on startOperation to keep rewriting asynchronous."
    ),
    "generateVoice": (
        "Use this synchronous endpoint for one continuous WAV of spoken text. For long scripts, cancellation, or "
        "batches prefer startOperation with kind=voice. Explicitly choose backend/mode from capabilities: "
        "AuK design needs text plus voice or a Design template; AuK clone needs text plus a WAV reference; "
        "Drama generate needs text, and Drama clone additionally needs a reference no longer than 15 seconds "
        "plus ref_text matching its spoken words. Delivery templates target text for Drama. "
        "API callers must trim oversized Drama references before submission using trimAudio; the UI trims picks "
        "automatically. Duration follows Drama's script; seconds/voice/convert are AuK controls. "
        "max_tokens is a safety cap per internal Drama chunk, not script length or target duration. "
        "Unconditioned Chinese can fail to finish: try another seed, simpler cues, or Clone with a clean reference. "
        "Raise the cap only for genuinely longer speech; it can prolong a looping generation."
    ),
    "readBatchItemResult": (
        "Fetch an item's result_url from a batch manifest as soon as that item completes; index starts at one. "
        "Image items return JSON/base64 PNG; video and voice items return raw MP4/WAV. "
        "Later item failure or cancellation preserves completed items, so download available items instead of "
        "rerunning the entire batch. A missing, not-yet-retained, or expired item returns 404."
    ),
    "trimAudio": (
        "Use this CPU-only endpoint to download a time selection, prepare a Clone reference, or send selected audio "
        "to video generation. Send PCM WAV bytes as bare base64 plus start_seconds/end_seconds within its duration. "
        "For a long Drama reference choose an excerpt of at most 15 seconds and transcribe only that excerpt. "
        "The response is WAV bytes at the original rate/channels/bit depth; X-Studio-Duration reports actual length. "
        "No model is loaded. Frame cuts use round(seconds*sample_rate) and must retain at least one frame."
    ),
    "readProgress": (
        "Use this legacy aggregate progress view only when you need the currently active sampler. "
        "Prefer readState/readOperation to track ownership, errors, cancellation, and completion for image, video, "
        "or voice. total=0 means unknown progress; do not divide by zero or interpret a sampler's last step as "
        "ready media. Wait for the operation's terminal status and result_url."
    ),
    "readRewriteState": (
        "Use this legacy view to display the current prompt-rewrite phase. It produces neither rewritten text nor "
        "media. Prefer readOperation to track a rewrite you started asynchronously, then fetch its result_url "
        "for the rewritten prompt. Use readState when you need to know which client owns active work."
    ),
    "cancelImage": (
        "Legacy workspace cancellation: asks the active image run to stop. Prefer cancelOperation with your own "
        "operation ID so you do not stop another client's work. A 204 response acknowledges the request; "
        "poll shared operation status for completion and retain any finished batch outputs."
    ),
    "cancelVideo": (
        "Legacy video cancellation: send the request_id used by the video request, or omit it to target the active "
        "render. Prefer cancelOperation with your operation ID for reliable ownership across clients. "
        "Poll status afterwards and download any already completed batch items."
    ),
    "cancelRewrite": (
        "Legacy rewrite cancellation: asks the active prompt rewrite to stop. Prefer cancelOperation with the "
        "rewrite operation's ID to target your own work. Poll operation status after the acknowledgement; "
        "cancelling a rewrite does not generate an image or video."
    ),
}
