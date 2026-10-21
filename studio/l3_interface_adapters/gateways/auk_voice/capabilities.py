"""AuK modes and templates.

Edit templates retain their measured instructions. Design templates adapt the
upstream cookbook and demo descriptions. They expose separate voice attributes.
"""

from studio.l1_entities.voice_capabilities import (
    Capabilities,
    Choice,
    Estimate,
    LoadingPolicy,
    ModeSpec,
    ParamSpec,
    Template,
)

SECONDS = ParamSpec(
    id="seconds",
    kind="number",
    default=0,
    minimum=0,
    maximum=120,
    step=0.5,
)
"""The length of the clip. 0 lets the adapter choose: from the text for clone and
design, from the input for edit. The model does not choose a length itself."""

CONVERT = ParamSpec(
    id="convert",
    kind="choice",
    default="tw2s",
    choices=(Choice("tw2s", "Traditional to Simplified"), Choice("off", "As written")),
)
"""Traditional Chinese is mispronounced as written: 颱風假 came back as 肥豐假. With
opencc tw2s first it read 6 of 6 hard words. tw2s changes characters only, so
Taiwan vocabulary survives."""

VOICE = ParamSpec(
    id="voice",
    kind="text",
    default="",
    hint="Describe the voice in detail: age, gender, tone, pace, volume, accent. "
    "Example: A woman in her thirties reading the evening news, calm, clear and warm, "
    "at a steady pace and medium volume, with a neutral American accent.",
)
"""The voice to build, in words, for design. Chinese or English. A one-line
description was read aloud in 3 of 3 seeds; a detailed one in 0 of 3."""


def _choice(id: str, default: str, *values: str) -> ParamSpec:
    return ParamSpec(id=id, kind="choice", default=default, choices=tuple(Choice(value, value) for value in values))


def _words(id: str, hint: str = "", default: str = "") -> ParamSpec:
    return ParamSpec(id=id, kind="text", default=default, hint=hint)


# Sources: Tencent-Hunyuan/AuK, commit 9481474f107ee4d8dec959b3aed05b0627cebbf8,
# docs/COOKBOOK.md section 1.2 and src/auk/infer/infer_gradio.py lines 25-45.
DESIGN_TEMPLATES = (
    Template(
        "Voice profile",
        "Define the speaker, texture, pace and delivery",
        "A {speaker} speaks with a {texture} voice. Use a {pace} pace and {delivery} delivery.",
        "Design",
        (
            _words("speaker", default="narrator"),
            _words("texture", default="warm and clear"),
            _words("pace", default="steady, moderate"),
            _words("delivery", default="natural, calm and precise"),
        ),
        target="voice",
    ),
    Template(
        "Conversation",
        "Describe the speaker, listener, setting and emotion",
        "A {speaker} addresses {listener} during {context}. The voice conveys {emotion}, "
        "with natural conversational pauses and clear, expressive phrasing.",
        "Design",
        (
            _words("speaker", default="friendly speaker"),
            _words("listener", default="a close friend"),
            _words("context", default="a quiet conversation at home"),
            _words("emotion", default="warmth and gentle concern"),
        ),
        target="voice",
    ),
    Template(
        "Narration",
        "Set the narrator, subject, pace and tone",
        "A {speaker} narrates {subject}. Use a {pace} pace and a {tone} tone, "
        "with clear diction, balanced volume and deliberate phrase endings.",
        "Design",
        (
            _words("speaker", default="documentary narrator"),
            _words("subject", default="an everyday discovery"),
            _words("pace", default="measured, unhurried"),
            _words("tone", default="warm and thoughtful"),
        ),
        target="voice",
    ),
    Template(
        "Commanding delivery",
        "Choose the speaker, audience, pace and emphasis",
        "A {speaker} addresses {audience} with confidence and clear projection. "
        "Use a {pace} pace, {emphasis}, and firm, controlled phrase endings.",
        "Design",
        (
            _words("speaker", default="confident leader"),
            _words("audience", default="a small team"),
            _words("pace", default="deliberate, varied"),
            _words("emphasis", default="strong emphasis on key words"),
        ),
        target="voice",
    ),
    Template(
        "Dramatic character",
        "Build a character, scene, texture and emotional shift",
        "A {character} speaks during {scene}. The voice has a {texture} texture. "
        "Convey {emotion}, with deliberate pauses, precise diction and expressive changes in intensity.",
        "Design",
        (
            _words("character", default="theatrical storyteller"),
            _words("scene", default="a surprising revelation"),
            _words("texture", default="rich and resonant"),
            _words("emotion", default="quiet confidence that grows into excitement"),
        ),
        target="voice",
    ),
    Template(
        "Emotional delivery",
        "Shape the speaker, emotion, pace and delivery",
        "A {speaker} expresses {emotion}. Use a {pace} pace and {delivery} delivery. "
        "Let the emotion shape the breath, pauses and phrase endings while keeping the words clear.",
        "Design",
        (
            _words("speaker", default="reflective speaker"),
            _words("emotion", default="restrained sadness"),
            _words("pace", default="slow, measured"),
            _words("delivery", default="soft, slightly trembling"),
        ),
        target="voice",
    ),
)


EDIT_TEMPLATES = (
    Template(
        "Replace words",
        "Change a word or phrase in the recording",
        "Replace '{original}' with '{new}'.",
        "Words",
        (_words("original"), _words("new")),
    ),
    Template(
        "Insert words",
        "Add words before a phrase",
        "Add '{text}' before '{anchor}'.",
        "Words",
        (_words("text"), _words("anchor")),
    ),
    Template(
        "Remove words",
        "Cut a phrase out. Check the words around the cut.",
        "Remove '{text}'.",
        "Words",
        (_words("text"),),
    ),
    Template(
        "Pitch",
        "Higher by 1 to 3 semitones",
        "Raise the pitch by {semitones} semitones.",
        "Sound",
        (ParamSpec(id="semitones", kind="number", default=2, minimum=1, maximum=3, integer=True, step=1),),
    ),
    Template(
        "Speed",
        "Slower or faster. The length changes with it.",
        "Adjust the speech speed to {speed}x.",
        "Sound",
        (_choice("speed", "1.5", "0.5", "0.75", "1.25", "1.5", "2.0"),),
        length_by="speed",
    ),
    Template(
        "Volume",
        "Louder by 5, 10 or 15 dB. It helps quiet audio most.",
        "Increase the volume by {decibels} dB.",
        "Sound",
        (_choice("decibels", "10", "5", "10", "15"),),
    ),
    Template(
        "Emotion",
        "Change how it is said, not what",
        "Change the emotion to {emotion}.",
        "Voice",
        (_choice("emotion", "calm", "happy", "angry", "sad", "fearful", "surprised", "disgusted", "calm", "excited"),),
    ),
    Template(
        "Timbre",
        "A voice described in words, keeping the content",
        'Keep the spoken content unchanged and change the timbre to: "{description}".',
        "Voice",
        (_words("description", "for example: a deep, gravelly older man"),),
    ),
    Template(
        "To whisper",
        "Soft speech, same speaker",
        "Convert this speech into a soft whisper while preserving the speaker and content.",
        "Voice",
    ),
    Template(
        "From whisper",
        "Normal speech, same speaker",
        "Convert this whispered speech into a normal speaking voice while preserving the speaker and content.",
        "Voice",
    ),
    Template(
        "Remove accent",
        "Keep the voice and the words",
        "Remove the regional accent while preserving the speaker's voice and content.",
        "Voice",
    ),
    Template(
        "Remove sounds",
        "Breaths, laughs, coughs or humming",
        "Remove all {sounds} from the audio.",
        "Voice",
        (_choice("sounds", "breaths", "breaths", "laughs", "coughs", "humming"),),
    ),
    Template(
        "Add a sound",
        "A laugh, cough or sigh at the start or end",
        "Add a {sound} at the {position} of the speech.",
        "Voice",
        (_choice("sound", "laugh", "laugh", "cough", "sigh"), _choice("position", "beginning", "beginning", "end")),
    ),
    Template(
        "Denoise",
        "Take out background noise, keep the rest",
        "Remove only the background noise, preserve everything else, and output audio of the same length.",
        "Clean-up",
    ),
    Template(
        "Dereverberate",
        "Take out room echo, keep the rest",
        "Remove only the room reverberation, preserve everything else, and output audio of the same length.",
        "Clean-up",
    ),
    Template(
        "Enhance",
        "Noise and echo together. The best choice for a poor recording.",
        "Preserve all speakers, remove noise and reverberation, and output clean speech of the same length.",
        "Clean-up",
    ),
    Template(
        "Fix muffled or clipped audio",
        "Repair a muffled or clipped recording",
        "Repair the {defect} and restore natural, clear speech.",
        "Clean-up",
        (_choice("defect", "muffling", "muffling", "clipping"),),
    ),
    Template(
        "Keep one speaker",
        "Name words that speaker says in the clip",
        'Keep only the speaker who says "{content}" and remove all other speakers.',
        "Clean-up",
        (_words("content", "words that speaker says in the clip"),),
    ),
    Template(
        "Voices only",
        "Keep speech and singing, drop the music",
        "Keep all human voices, including speech and singing, and remove everything else.",
        "Clean-up",
    ),
    Template(
        "Vocals only",
        "Keep the singing, drop the band",
        "Keep only the singing voice and remove everything else.",
        "Clean-up",
    ),
    # The other direction of the same task, measured on a made mix of speech and three steady tones:
    # this wording returned the tones alone, with none of the speech's energy above 400 Hz and the
    # tones' own level. An instruction that said "keep only the instrumental music" kept the voice and
    # only made it quieter, so the wording is the whole of it.
    Template(
        "Music only",
        "Keep the band, drop the voices",
        "Remove the singing and speaking voice and keep everything else.",
        "Clean-up",
    ),
)


def auk_capabilities(variant: str) -> Capabilities:
    """`variant` is "flash", 4 steps, or "base", 32 steps. They load different weights."""
    # Measured on an M1 Pro, 32 GB, 8-bit, one run each, the engine already loaded:
    #   flash  clone 24s in 23.2s (0.97), edits 11.6s in 14 to 27s (1.2 to 2.3)
    #   base   clone 24s in 115.9s (4.83), edit 24s in 164.0s (6.83)
    # Loading is paid once, when the child starts: 53s cold, 4s with the weights cached.
    rtf, overhead = (1.3, 2.0) if variant == "flash" else (5.5, 2.0)
    estimate = Estimate(rtf=rtf, overhead=overhead)
    return Capabilities(
        loading=LoadingPolicy(
            policy="download_on_first_use",
            repository="smcleod/AuK-MLX-8bit",
            revision="abffd38adf7d9f0a94822e7c153e0c4ef70ef213",
            note="The first Voice run downloads pinned weights if missing. Later runs reuse the cache.",
        ),
        backend_id="auk" if variant == "flash" else "auk_base",
        name="AuK Flash" if variant == "flash" else "AuK",
        badge="int8",
        max_batch=16,
        modes=(
            ModeSpec(
                id="clone",
                label="Clone",
                params=(SECONDS, CONVERT),
                text_hint="What the voice in the reference clip should say.",
                text_required="Write what the voice should say.",
                min_references=1,
                max_references=1,
                estimate=estimate,
            ),
            ModeSpec(
                id="design",
                label="Design",
                params=(VOICE, SECONDS, CONVERT),
                text_hint="What the voice should say. Describe the voice under voice.",
                text_required="Write what the voice should say.",
                templates=DESIGN_TEMPLATES,
                estimate=estimate,
            ),
            ModeSpec(
                id="edit",
                label="Edit",
                params=(SECONDS, CONVERT),
                text_hint="What to change in the clip, as an instruction.",
                text_required="Write what to change.",
                templates=EDIT_TEMPLATES,
                min_references=1,
                max_references=1,
                estimate=estimate,
            ),
        ),
    )
