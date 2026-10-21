"""Only the Drama-3 controls exposed and checked by the selected MLX engine."""

from studio.l1_entities.voice_capabilities import Capabilities, Estimate, LoadingPolicy, ModeSpec, ParamSpec, Template

SAMPLING = (
    ParamSpec(
        "temperature",
        "number",
        0.7,
        minimum=0.1,
        maximum=1.5,
        step=0.05,
        hint="Higher values vary the performance more.",
    ),
    ParamSpec(
        "top_p",
        "number",
        0.7,
        minimum=0.1,
        maximum=1,
        step=0.05,
        hint="Probability mass retained when choosing the next audio token.",
    ),
    ParamSpec(
        "top_k", "number", 30, minimum=1, maximum=100, integer=True, step=1, hint="Number of candidate audio tokens."
    ),
    ParamSpec(
        "max_tokens",
        "number",
        1024,
        minimum=64,
        maximum=2048,
        integer=True,
        step=1,
        hint="Safety limit per internal script chunk, not a target duration. A limit reached before completion fails the job.",
    ),
)
TRANSCRIPT = ParamSpec("ref_text", "text", "", required=True, hint="Exact words spoken in the reference recording.")
TEMPLATES = (
    Template(
        "Whisper",
        "Direct a quiet delivery without reading the direction aloud.",
        "[whispers] {script}",
        "Delivery",
        (ParamSpec("script", "text", "Keep your voice down. Someone is listening."),),
    ),
    Template(
        "Excited",
        "Direct an enthusiastic delivery.",
        "[excited] {script}",
        "Delivery",
        (ParamSpec("script", "text", "We finally made it! This is wonderful!"),),
    ),
)
# M5 Pro 64 GiB, eight-bit weights, seed 7, native 44.1 kHz, 0.5s codec chunks:
# warm whisper 3.07s audio / 2.72s wall; excited 4.09 / 4.66;
# cached Clone 3.39 / 3.87. Primitive load 20.61s; first generation 16.00s.
ESTIMATE = Estimate(rtf=1.2, overhead=34)


def drama_capabilities():
    return Capabilities(
        backend_id="drama3",
        name="Drama-3",
        badge="",
        max_batch=16,
        default_mode="generate",
        reference_sample_rate=44100,
        max_reference_seconds=15,
        loading=LoadingPolicy(
            "download_on_first_use",
            "mlx-community/fish-audio-drama-3-8bit",
            "fedc7cc92bab5a180709cbaae6208d10b390bb97",
            "The first run downloads about 42 GB of pinned weights. Duration follows the script. Delivery cues go inside square brackets. Unconditioned Chinese can fail to finish; try a reference voice or another seed.",
        ),
        modes=(
            ModeSpec(
                "generate",
                "Generate",
                SAMPLING,
                text_hint="Write a script. Add delivery cues inline, such as [whispers].",
                templates=TEMPLATES,
                estimate=ESTIMATE,
            ),
            ModeSpec(
                "clone",
                "Clone",
                (*SAMPLING, TRANSCRIPT),
                min_references=1,
                max_references=1,
                text_hint="Write the new words. Inline delivery cues are optional.",
                templates=TEMPLATES,
                estimate=ESTIMATE,
            ),
        ),
    )
