"""Official prompting references, with the local adapter boundary made explicit."""

FISH = "https://docs.fish.audio"
AUK = "https://github.com/Tencent-Hunyuan/AuK"
BOOK = AUK + "/blob/main/docs/COOKBOOK.md"

# Checked 2026-10-22 against the publishers' documentation indexes and repositories.
# These are references, not a declaration that every upstream feature is exposed.
VOICE_PROMPT_GUIDES = [
    {
        "models": ["drama3"],
        "title": "Drama-3 direction guide",
        "url": FISH + "/features/text-to-speech/drama-3",
        "scope": "primary",
        "topics": "Delivery, sounds, pauses, word-scoped tags, language changes and phonemes.",
    },
    {
        "models": ["drama3"],
        "title": "Drama-3 model examples",
        "url": "https://huggingface.co/fishaudio/drama-3#example-usage",
        "scope": "upstream examples",
        "topics": "Point cues and continuation editing; Studio does not expose continuation history.",
    },
    {
        "models": ["drama3"],
        "title": "English pronunciation",
        "url": FISH + "/developer-guide/core-features/fine-grained-control/english",
        "scope": "upstream syntax",
        "topics": "CMU Arpabet notation; test the desired pronunciation on the pinned MLX model.",
    },
    {
        "models": ["drama3"],
        "title": "Chinese pronunciation",
        "url": FISH + "/developer-guide/core-features/fine-grained-control/chinese",
        "scope": "upstream syntax",
        "topics": "Tone-number pinyin; local unconditioned Chinese has measured completion limitations.",
    },
    {
        "models": ["drama3"],
        "title": "Japanese pronunciation",
        "url": FISH + "/developer-guide/core-features/fine-grained-control/japanese",
        "scope": "upstream syntax",
        "topics": "Romaji and pitch notation; not independently certified by Studio.",
    },
    {
        "models": ["drama3"],
        "title": "Recording a clone reference",
        "url": FISH + "/developer-guide/best-practices/voice-cloning",
        "scope": "shared recording advice",
        "topics": "Recording quality; its hosted recording lengths do not override Studio's 15-second limit.",
    },
    {
        "models": ["drama3"],
        "title": "Emotion vocabulary",
        "url": FISH + "/developer-guide/core-features/emotions",
        "scope": "S2 background",
        "topics": "Additional cue ideas. This page describes S2 and legacy S1; prefer the Drama-3 guide for syntax.",
    },
    {
        "models": ["drama3"],
        "title": "Fine control background",
        "url": FISH + "/developer-guide/core-features/fine-grained-control",
        "scope": "mixed-version background",
        "topics": "Pronunciation and older control forms; avoid copying legacy parenthesis syntax into Drama scripts.",
    },
    {
        "models": ["drama3"],
        "title": "Fish documentation index",
        "url": FISH + "/llms.txt",
        "scope": "publisher index",
        "topics": "Discover current canonical documentation; hosted API fields are not Studio fields.",
    },
    {
        "models": ["drama3"],
        "title": "Open-weight inference",
        "url": "https://speech.fish.audio/inference/#drama-3",
        "scope": "upstream runtime",
        "topics": "Reference/transcript examples for the official runtime; Studio uses a separate MLX adapter.",
    },
    {
        "models": ["drama3"],
        "title": "Drama-3 serving cookbook",
        "url": "https://sgl-project.github.io/sglang-omni/cookbook/fishaudio_drama3.html",
        "scope": "model-card-linked integration",
        "topics": "More request examples; reference limits, streaming and performance are specific to that runtime.",
    },
    {
        "models": ["drama3"],
        "title": "Drama-3 vLLM recipe",
        "url": "https://recipes.vllm.ai/fishaudio/drama-3",
        "scope": "model-card-linked integration",
        "topics": "Alternative serving examples, not parameters accepted by this Studio.",
    },
    {
        "models": ["auk", "auk_base"],
        "title": "AuK instruction cookbook",
        "url": BOOK,
        "scope": "primary",
        "topics": "Bilingual instructions across generation, editing, restoration and separation.",
    },
    {
        "models": ["auk", "auk_base"],
        "title": "AuK cloning and voice design",
        "url": BOOK + "#1-speech-generation",
        "scope": "task instructions",
        "topics": "Map the target script to text and the designed speaker to voice; Studio builds the model instruction.",
    },
    {
        "models": ["auk", "auk_base"],
        "title": "AuK word and lyric edits",
        "url": BOOK + "#2-content-editing",
        "scope": "task instructions",
        "topics": "Edit instructions; upstream lyric recipes have input requirements and are not all locally validated.",
    },
    {
        "models": ["auk", "auk_base"],
        "title": "AuK acoustic edits",
        "url": BOOK + "#3-acoustic-editing",
        "scope": "task instructions",
        "topics": "Pitch, speed and volume instructions for Edit.",
    },
    {
        "models": ["auk", "auk_base"],
        "title": "AuK expressive edits",
        "url": BOOK + "#4-paralinguistic-editing",
        "scope": "task instructions",
        "topics": "Emotion, timbre, accent, nonverbal sounds and whisper conversion.",
    },
    {
        "models": ["auk", "auk_base"],
        "title": "AuK restoration and isolation",
        "url": BOOK + "#5-enhancement--separation",
        "scope": "task instructions",
        "topics": "Cleanup and source-isolation recipes; use an offered Edit template when available.",
    },
    {
        "models": ["auk", "auk_base"],
        "title": "AuK demo prompts",
        "url": AUK + "/blob/main/src/auk/infer/infer_gradio.py",
        "scope": "publisher examples",
        "topics": "Concrete English/Chinese instructions paired with example source audio and durations.",
    },
    {
        "models": ["auk", "auk_base"],
        "title": "AuK Prompt Enhancer",
        "url": AUK + "#prompt-enhancer",
        "scope": "upstream tooling",
        "topics": "Optional upstream instruction preparation; Studio does not expose this CLI tool or a PE request flag.",
    },
    {
        "models": ["auk", "auk_base"],
        "title": "AuK ComfyUI notes",
        "url": AUK + "/blob/main/docs/COMFYUI.md",
        "scope": "upstream integration",
        "topics": "Duration and Flash examples; ComfyUI's shared 30-second budget is not Studio's duration contract.",
    },
    {
        "models": ["auk", "auk_base"],
        "title": "AuK authors' audio demos",
        "url": "https://auk-project.github.io/",
        "scope": "authors' demonstrations",
        "topics": "Listen to task examples; the site is maintained by the paper authors.",
    },
    {
        "models": ["auk_base"],
        "title": "AuK model card",
        "url": "https://huggingface.co/tencent/AuK",
        "scope": "publisher model card",
        "topics": "Base-model context and links; use Studio's pinned MLX settings rather than copying inference flags.",
    },
    {
        "models": ["auk"],
        "title": "AuK Flash model card",
        "url": "https://huggingface.co/tencent/AuK-Flash",
        "scope": "publisher model card",
        "topics": "Distilled variant context; Studio fixes the Flash sampler to four steps.",
    },
]

VOICE_START_HERE = (
    "Official prompting: [Drama-3 direction guide](" + VOICE_PROMPT_GUIDES[0]["url"] + ") and "
    "[AuK instruction cookbook](" + BOOK + "). See the Voice tag's reference index and "
    "the machine-readable x-voice-prompt-guides catalogue for task-specific links and scope notes."
)

VOICE_API_CONTRACT = """Choose backend explicitly, then use only its discovered modes and parameters.

| Contract | Drama-3 (drama3) | AuK (auk_base) / AuK Flash (auk) |
|---|---|---|
| Modes / default | generate, clone / generate | design, clone, edit / design |
| No-reference speech | text with optional inline direction | text plus voice or a Design template |
| Clone | text, reference, exact ref_text | text and reference; no transcript required |
| Controls | temperature, top_p, top_k, max_tokens | seconds, convert; voice for Design |
| Reference / native WAV rate | at most 15 seconds / 44.1 kHz | at most 120 seconds / 24 kHz |
| Duration / progress | script-driven / indeterminate during synthesis | seconds=0 selects automatically / sampler steps |

Drama sampling defaults match the pinned MLX Audio implementation: temperature=0.7, top_p=0.7
and top_k=30. Studio sets max_tokens=2048 per internal chunk, increased from the engine default of
1024 to allow more completion headroom. It remains a ceiling, not a target length; looping output may
run longer before failing. These are implementation and product defaults, not a Fish Audio
recommendation established as best for every task. See the [pinned MLX source](https://github.com/Blaizzy/mlx-audio/blob/2209e6d76c18d0a24f7ff64d35b4176258acd909/mlx_audio/tts/models/fish_drama3/drama3.py).
AuK uses the upstream 32-step setting; Flash uses its fixed 4-step path. See the
[AuK inference implementation](https://github.com/Tencent-Hunyuan/AuK/blob/9481474f107ee4d8dec959b3aed05b0627cebbf8/src/auk/infer/infer_gradio.py)
and [official Flash setup](https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COMFYUI.md).
These settings have real-run coverage but have not been proven optimal by a systematic quality sweep.
Adapter chunking, voice-description wording and Chinese character conversion have targeted experimental
evidence; this does not establish universally best model settings.

Both use one model per ordered batch, at most 16 items, and the same operation/result/cancel contract.
The API checks supported modes, required inputs, declared parameter values, templates, seeds and decoded WAV limits.
Unknown top-level fields and parameters not declared by the selected mode are currently ignored, not rejected.
For example, seconds does not set Drama duration and temperature does not tune AuK. Do not rely on ignored fields.
Unknown template fields do reject the request. A supplied reference is rejected in modes that accept none.
Send backend and mode explicitly for schema validation: an omitted backend depends on server state and cannot
be fully checked by a static schema. Batch items inherit defaults; validate each merged item as a VoiceRequest.
Synchronous invalid requests return 400. Async 202 only acknowledges acceptance; inspect terminal status/error
for validation failures in the worker. API references over the model limit must be trimmed explicitly;
UI trimming is not applied to API payloads.
"""

VOICE_PROMPT_BOUNDARY = """Read the primary model guide first, then discover the selected Studio model/mode.
For Drama put spoken words and inline directions in text. For AuK Design put only spoken words in text and
speaker attributes in voice, or select an offered template. For AuK Edit put the change instruction in text
and supply reference.wav_base64. Never paste upstream ChatML, CLI commands, or hosted request envelopes into text.

The guides describe upstream systems too. Studio does not expose Fish hosted voice IDs/reference_id arrays,
multi-reference speaker casting, previous_takes/continuation editing, streaming responses, pronunciation
dictionary management, or an AuK Prompt Enhancer flag. Additional fields are ignored rather than enabling them.
Delivery/phoneme markup stays in the script passed to the local engine, but every upstream tag/language has
not been tested on the pinned MLX checkpoint. Language-switch markup is experimental upstream; local
unconditioned Chinese has measured completion failures. Prefer short probes and a clean reference where needed.
Upstream reference lengths, normalization controls, duration budgets and serving speeds do not override
Studio discovery. Links were checked 2026-10-22; current upstream pages may evolve beyond our pinned engines.
"""

VOICE_PROMPT_REFERENCES = (
    "## Official Voice prompting references\n\n" + VOICE_PROMPT_BOUNDARY + "\n"
    "| Model | Reference | Scope and use |\n|---|---|---|\n"
    + "\n".join(
        f"| {', '.join(item['models'])} | [{item['title']}]({item['url']}) | {item['scope']}: {item['topics']} |"
        for item in VOICE_PROMPT_GUIDES
    )
)
