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
STEP_COST = 4.0
STEP_EXPONENT = 1.25
GENERATE_OVERHEAD = 3  # per image; the model is already resident
EDIT_OVERHEAD = 20  # once per batch; the child may have to load a pipeline

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
GUIDANCE = ParamSpec(id="guidance", kind="number", default=1.0, minimum=0, step=0.5)
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
CFG = ParamSpec(id="cfg", kind="number", default=1.0, minimum=1, maximum=10, step=0.5)

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
    estimate=Estimate(STEP_COST, STEP_EXPONENT, EDIT_OVERHEAD, overhead_per_image=False, match_cap=EDIT_MATCH_CAP),
)


def qwen21_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="qwen21", name="Qwen-Image-2.1", badge=badge, modes=(GENERATE, EDIT), max_batch=MAX_BATCH
    )
