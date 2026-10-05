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

# Cost, before you spend it. Measured 2026-10-05 on an M5 Pro, 64 GB, bf16, two
# points at each size 20 steps apart so the fixed cost and the per-step cost
# separate. The low point is 2 steps, not 1: mflux refuses a single step.
#
#   seconds per step   0.26 MP   0.59 MP   1.05 MP
#   generate            not re-measured; see below
#   edit, 1 reference     0.82      2.07      5.41
#
#   fixed cost            14.6s     15.9s     53.9s
#
# The edit figures are the in-process mflux engine, which replaced the diffusers
# child. That child's curve was 1.31, 3.77 and 9.90 s/step on the same tiers, so
# the swap is about twice as fast per step, and it peaks at 36 to 46 GB against
# the 38.7 GiB the child held.
#
# A least-squares power law through the three points gives 4.72 and 1.336, and it
# lands within 13% at the worst of them. The cost is superlinear in pixels because
# attention is quadratic in token count, which is what the exponent carries.
#
# **The generate half is measured too**, 2026-10-05, same method and machine. The
# first row is left out of the fit: it carries the model build, which the first run
# of a process pays and the rest do not.
#
#   seconds per step   0.26 MP   0.59 MP   1.05 MP
#   generate            (10.0s)     1.41      3.40     fixed cost 1.3s and 7.9s
#
# The pin moved to mflux 0.21.0 while this was measured, which added a text-prefix
# KV cache and a fused Metal kernel, so the pair is roughly half what it was: the
# old 6.1 and 1.55 predicted 2.73 s/step at 0.59 MP against 1.41 now.
GENERATE_STEP_COST = 3.15
GENERATE_STEP_EXPONENT = 1.53
EDIT_STEP_COST = 4.72
EDIT_STEP_EXPONENT = 1.336
# The fixed cost before the first step, which is the prompt and image encode. It is
# not flat: 14.6s and 15.9s at the two small tiers, 53.9s at 1.05 MP, and 70.8s for
# ten references at 0.59 MP. One number cannot follow a size and a reference count,
# so this sits between them and errs high. Measured 2026-10-05.
#
# Reference growth is the same problem. Going from one reference to two multiplies
# the step cost by 1.30, and one to ten only by 2.09, so the growth is sublinear and
# a single multiplier cannot hold both ends. 0.20 is fitted at two references, where
# a marked edit lives, because a mark rides as one more reference. It reads 8% short
# there and 34% long at ten. Measured 2026-10-05 at 0.59 MP.
REFERENCE_STEP_GROWTH = 0.20  # one more reference multiplies the step cost by 1 + this
GENERATE_OVERHEAD = 3  # per image; the model is already resident. Measured 1.3s at 0.59 MP and 7.9s at 1.05 MP
EDIT_OVERHEAD = 30

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
    # Measured 2026-10-05 on the in-process mflux engine, one seed and 20 steps, on a
    # drawn shape whose edge the mark matched: the change landed 15.8x more inside the
    # marked area than outside it, and the rest of the frame moved by 4.3 of 255.
    #
    # The engine swap is a wash on this, not a win. On the fixture the old figure came
    # from, the diffusers child this replaced read 37.5x against 28.8x here, and on a
    # mark over a uniform surface, where only the mark can bound the change, 2.4x
    # against 3.1x. One seed on one fixture settles neither direction, so neither claim
    # is made. PROMPTS.md holds the tables and their limits.
    region_marking=True,
)


def qwen21_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="qwen21", name="Qwen-Image-2.1", badge=badge, modes=(GENERATE, EDIT), max_batch=MAX_BATCH
    )
