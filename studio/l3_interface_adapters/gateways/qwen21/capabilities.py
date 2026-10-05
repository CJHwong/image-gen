"""What the Qwen-Image-2.1 backend offers the page, and the limits the core checks."""

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.prompt_aids import EDIT_TEMPLATES, GENERATE_LOOKS, GENERATE_TEMPLATES
from studio.l3_interface_adapters.gateways.qwen_image_sizes import (
    EDIT_MATCH_CAP,
    EDIT_RESOLUTIONS,
    SIZES,
)

MATCH = "match"
MAX_REFERENCES = 10
MAX_BATCH = 4

# Cost, before you spend it. Measured 2026-09-27 on an M5 Pro, 64 GB, three
# repeats at each point, one step and twenty steps apart so the fixed cost and
# the per-step cost separate:
#
#   seconds per step   0.26 MP   0.59 MP   1.05 MP
#   mflux t2i             0.69      3.37      5.76
#   edit, 1 reference     1.31      3.77      9.90
#
# The generate numbers still describe the code that runs: the text-to-image half
# did not change. The cost is superlinear in pixels because attention is
# quadratic in token count, which is what the exponent carries.
#
# **The edit numbers describe the engine this repo removed.** They came from the
# diffusers pipeline in the child process, which had a different fixed cost, and
# the mask was a second image it had to encode. Editing now runs on mflux in this
# process and these constants must be re-measured against it: the page's own
# learned rate corrects them after the first run on a device, so a wrong constant
# costs one misleading estimate rather than a wrong run, but it is still wrong.
#
# Run-to-run spread on this machine is large: three runs of one size and one
# seed differ by up to 20% at 1.05 MP, and the 0.59 MP generate point spread
# 44.7s to 76.5s. The generate fit lands inside 20%, and only one point
# disagrees, so it is fitted across all three rather than around it.
GENERATE_STEP_COST = 6.1
GENERATE_STEP_EXPONENT = 1.55
EDIT_STEP_COST = 8.8
EDIT_STEP_EXPONENT = 1.44
# Measured 2026-09-27 by timing the child's own steps, so the encode was separated from
# the denoising. Between step 0, which says the engine started, and step 1 sits the prompt
# and image encode, and it was 30 to 90 seconds whatever the reference's size, because the
# processor resized to a token budget. One more reference adds a share of the step cost,
# and the encode rides in the overhead, counted per image rather than per batch because
# every image encodes its own. The engine is gone; the shape of this may not survive it.
#
# The same matrix measured the two parts of that. At 0.59 MP a second reference took the
# step cost from 3.77 to 4.43, a factor of 1.175, so the share is 0.175 rather than the
# 0.6 an earlier single-reference measurement gave.
REFERENCE_STEP_GROWTH = 0.175  # one more reference multiplies the step cost by 1 + this
GENERATE_OVERHEAD = 3  # per image; the model is already resident
# The encode before step 1. The child's figure counted a pipeline build paid once
# per child, and the matrix then measured it at 4.1s, 10.2s and 19.9s for 0.26,
# 0.59 and 1.05 MP. 20 was the top of that range, chosen because a flat number
# cannot follow a size and this is the side to be wrong on. The new engine has no
# pipeline to build, so the number is too high.
EDIT_OVERHEAD = 20

STEPS = ParamSpec(id="steps", kind="number", default=40, minimum=1, maximum=100, integer=True, step=1)
NEGATIVE = ParamSpec(id="negative", kind="text", default="")
SIZE = ParamSpec(
    id="size",
    kind="choice",
    default="1024x1024",
    choices=(
        *(Choice(f"{width}x{height}", label) for label, width, height in SIZES),
        Choice(MATCH, "Match reference (about 1 MP)"),
    ),
)
# A negative prompt works only through true CFG, which needs guidance above 1
# and runs two passes per step. 2.5 is the value PROMPTS.md tested it at.
GUIDANCE = ParamSpec(id="guidance", kind="number", default=1.0, minimum=0, maximum=10, step=0.5, with_negative=2.5)
# mflux skips this share of the schedule: init_time_step = max(1, int(steps *
# strength)). RMS distance from the reference, one pear at 8 steps: 17.1 at
# 0.15, 4.0 at 0.55, 2.5 at 0.85, and 74.5 with no reference. Every strength
# stays close to the reference, so drop the reference when the prompt should win.
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
CFG = ParamSpec(id="cfg", kind="number", default=1.0, minimum=1, maximum=10, step=0.5, with_negative=2.5)

GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, STEPS, GUIDANCE, STRENGTH, NEGATIVE),
    max_references=1,  # mflux's generate_image takes one image_path
    prompt_hint="Describe the image. Put any text you want rendered in quotes.",
    looks=GENERATE_LOOKS,
    templates=GENERATE_TEMPLATES,
    estimate=Estimate(GENERATE_STEP_COST, GENERATE_STEP_EXPONENT, GENERATE_OVERHEAD, overhead_per_image=True),
)
EDIT = ModeSpec(
    id="edit",
    label="Edit",
    params=(RESOLUTION, STEPS, CFG, NEGATIVE),
    min_references=1,
    max_references=MAX_REFERENCES,
    prompt_hint="For example: make it night, with the lights on",
    prompt_required="An edit instruction is required.",
    templates=EDIT_TEMPLATES,
    estimate=Estimate(
        EDIT_STEP_COST,
        EDIT_STEP_EXPONENT,
        EDIT_OVERHEAD,
        # Every image of a batch is its own run, so each one pays the encode before
        # its first step. The model stays resident, so there is no pipeline build
        # to count. See EDIT_OVERHEAD above.
        overhead_per_image=True,
        match_cap=EDIT_MATCH_CAP,
        per_reference=REFERENCE_STEP_GROWTH,
    ),
    # Measured 2026-09-26 with the mask and the sentence the page sends, one seed
    # and 20 steps, on a drawn scene: the recolour was exact, an unmarked object
    # and the background were unchanged, and the change landed 24.2x more inside
    # the marked area than outside it. PROMPTS.md holds the table and its limits.
    region_marking=True,
)


def qwen21_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="qwen21", name="Qwen-Image-2.1", badge=badge, modes=(GENERATE, EDIT), max_batch=MAX_BATCH
    )
