"""What the Qwen-Image-2.1 backend offers the page, and the limits the core checks."""

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.prompt_aids import EDIT_TEMPLATES, GENERATE_LOOKS, GENERATE_TEMPLATES

MATCH = "match"
MAX_REFERENCES = 10
MAX_BATCH = 4

# Every shape offers the same four tiers: about 0.25, 0.6 and 1 MP, then the
# large size the list started with. Each keeps its exact ratio on a 16-pixel
# grid. The model trains around 1 MP, so that tier is the default for a shape.
SIZES = (
    ("1024 x 1024", 1024, 1024),
    ("512 x 512", 512, 512),
    ("768 x 768", 768, 768),
    ("1328 x 1328", 1328, 1328),
    ("768 x 432 (16:9)", 768, 432),
    ("1024 x 576 (16:9)", 1024, 576),
    ("1280 x 720 (16:9)", 1280, 720),
    ("1664 x 928 (16:9)", 1664, 928),
    ("432 x 768 (9:16)", 432, 768),
    ("576 x 1024 (9:16)", 576, 1024),
    ("720 x 1280 (9:16)", 720, 1280),
    ("928 x 1664 (9:16)", 928, 1664),
    ("576 x 432 (4:3)", 576, 432),
    ("896 x 672 (4:3)", 896, 672),
    ("1152 x 864 (4:3)", 1152, 864),
    ("1472 x 1104 (4:3)", 1472, 1104),
    ("432 x 576 (3:4)", 432, 576),
    ("672 x 896 (3:4)", 672, 896),
    ("864 x 1152 (3:4)", 864, 1152),
    ("1104 x 1472 (3:4)", 1104, 1472),
)

# The edit pipeline treats output_resolution as an area budget, not a side: it
# calls calculate_dimensions(res * res, reference aspect ratio). So the shape
# always follows the reference, and this number only sets how many pixels. A
# 1280x720 reference comes back 1280x704, the multiple of 32 the pipeline needs.
EDIT_RESOLUTIONS = (1024, 768, 512, 1328)

# An edit usually wants its input back at the size it came in at, so "match"
# is the default. The cap is there because the output size drives the whole
# denoising cost: a 2560x1440 screenshot would ask for about 1920, which is far
# past anything this machine renders in reasonable time.
EDIT_MATCH_CAP = 1328

# Cost, before you spend it. Measured seconds per step on an M5 Pro, 64 GB:
#
#   megapixels   0.26   0.59   1.05   1.60   1.75
#   mflux t2i    1.01   1.79   3.32      -   6.14
#   edit         0.76   1.87   3.52   7.95   7.40
#
# The cost is superlinear in pixels, because attention is quadratic in token
# count. A flat rate per pixel fit the small sizes and then under-promised
# badly at the top: it called a run 4 minutes that took 345 seconds. An
# exponent of 1.25 holds both engines inside 3.3 to 4.4, so one curve covers
# both. The constant sits at the high end on purpose, because an estimate that
# runs short is worse than one that runs long. The page replaces it with the
# rate it sees once a run is under way.
#
# More references cost more, because each is a second vision context. Measured
# again 2026-09-26 on the same machine, edit mode alone, 20 steps, one seed:
#
#   megapixels    0.26   0.59   1.05
#   1 reference   0.83   1.80   4.23
#   2 references  1.21   2.67   5.71
#   10 references 2.99      -      -
#
# A second image multiplies the step cost by 1.35 to 1.48, so per_reference is
# 0.45. Ten came in at 3.6 times where a straight line predicts 5.05, so the
# line runs long rather than short, which is the side to be wrong on. A marked
# region is one more image, and that is what a marked run sends. This run put
# 1.05 megapixels at 4.23 against the 3.52 in the table above, and the same
# shape has taken 130 s and 207 s in one session, so the constant stays as the
# first table fitted it rather than moving on one shape.
STEP_COST = 4.0
STEP_EXPONENT = 1.25
# Measured 2026-09-26 by timing the child's own steps, so the encode is separated from the
# denoising. Between step 0, which says the engine started, and step 1 sits the prompt and
# image encode, and it is 30 to 90 seconds whatever the reference's size, because the
# processor resizes to a token budget. The mask is a second image and it costs about half
# again: at 1024 output, per step 3.57 becomes 5.66 with it, and the encode 28.6 becomes
# 70.5. So one more reference adds 0.6 of the step cost, and the encode rides in the
# overhead, counted per image rather than per batch because every image encodes its own.
REFERENCE_STEP_GROWTH = 0.6  # one more reference adds this share to the step cost
GENERATE_OVERHEAD = 3  # per image; the model is already resident
EDIT_OVERHEAD = 100  # per image: the pipeline build, then the encode before step 1

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
    estimate=Estimate(STEP_COST, STEP_EXPONENT, GENERATE_OVERHEAD, overhead_per_image=True),
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
        STEP_COST,
        STEP_EXPONENT,
        EDIT_OVERHEAD,
        # Every image of a batch is its own run through the child, so each one pays the
        # encode before its first step. The pipeline build is paid once and counted here
        # once per image, which runs long for a batch and is the side to be wrong on.
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
