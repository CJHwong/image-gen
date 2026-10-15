"""The controls and measured run costs for the official Qwen Turbo checkpoint."""

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.qwen_image_sizes import EDIT_MATCH_CAP, EDIT_RESOLUTIONS, SIZES

MATCH = "match"
MAX_BATCH = 1

SIZE = ParamSpec(
    id="size",
    kind="choice",
    default="1024x1024",
    choices=(
        *(Choice(f"{width}x{height}", label) for label, width, height in SIZES),
        Choice(MATCH, "Match reference (about 1 MP)"),
    ),
)
STEPS = ParamSpec(id="steps", kind="number", default=8, minimum=8, maximum=8, integer=True, step=1)
STRENGTH = ParamSpec(id="strength", kind="number", default=0.4, minimum=0.05, maximum=1, step=0.05)
RESOLUTION = ParamSpec(
    id="resolution",
    kind="choice",
    default=MATCH,
    choices=(
        Choice(MATCH, "Match the reference"),
        *(Choice(str(side), f"about {side} x {side}") for side in EDIT_RESOLUTIONS),
    ),
)

# End-to-end times measured 2026-10-15 on Office's M5 Pro, 64 GB, BF16.
# Each value has two runs after a warmup. Pixel areas are 0.26, 0.59 and 1.05 MP.
#
#   Generate, no starting image, 8 steps: 10.2-10.7, 17.4-26.1, 32.7-34.0s
#   Generate, ref at 0.4, 5 steps: 3.8-3.8, 8.4-8.8, 22.7-25.9s
#   Generate, ref at 1.0, 0 steps: 1.0-1.0, 1.8-1.8, 3.0-3.1s
#   Edit, 1 reference, 8 steps: 9.9-9.9, 27.8-30.5, 50.8-55.7s
#
# The reference fit uses both strengths. Its overhead captures image setup.
# Mflux starts at int(8 * strength), with at least one skipped step. The page
# scales its estimate by the remaining steps. Edit uses its declared maximum.
# The estimates are 10.6, 21.0 and 34.0s for text generation, 3.3, 8.8 and
# 24.3s for reference generation at strength 0.4, and 10.2, 27.4 and 55.2s for edit.
GENERATE_ESTIMATE = Estimate(4.083, 0.840, 0, overhead_per_image=True)
GENERATE_REFERENCE_ESTIMATE = Estimate(
    4.030,
    2.066,
    2.030,
    overhead_per_image=True,
    strength_scales_steps=True,
)
EDIT_ESTIMATE = Estimate(6.514, 1.220, 0, overhead_per_image=True, match_cap=EDIT_MATCH_CAP)

GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, STEPS, STRENGTH),
    max_references=1,
    prompt_hint="Describe the image. Put any text you want rendered in quotes.",
    estimate=GENERATE_ESTIMATE,
    reference_estimate=GENERATE_REFERENCE_ESTIMATE,
)
EDIT = ModeSpec(
    id="edit",
    label="Edit",
    params=(RESOLUTION, STEPS),
    min_references=1,
    max_references=1,
    prompt_hint="For example: change the light to a warm evening glow",
    prompt_required="An edit instruction is required.",
    estimate=EDIT_ESTIMATE,
)


def qwen21_turbo_capabilities(badge: str = "bf16") -> Capabilities:
    return Capabilities(
        backend_id="qwen21_turbo",
        name="Qwen-Image-2.1-Turbo",
        badge=badge,
        modes=(GENERATE, EDIT),
        max_batch=MAX_BATCH,
        description="Official 8-step checkpoint. Prompt aids await local validation.",
    )
