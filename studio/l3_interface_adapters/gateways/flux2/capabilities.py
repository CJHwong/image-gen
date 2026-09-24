"""What the FLUX.2 klein-base-9B backend offers the page, and the limits the core checks."""

from dataclasses import replace

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.prompt_aids import EDIT_TEMPLATES, GENERATE_TEMPLATES, pick_looks

MATCH = "match"
MAX_BATCH = 4
# Four references at 512 ran at 9.71 s/step against 3.63 with one. More was not tried.
MAX_REFERENCES = 4

# Three tiers per shape, on the 16-pixel grid the model needs, 1 MP the largest.
SIZES = (
    ("1024 x 1024", 1024, 1024),
    ("512 x 512", 512, 512),
    ("768 x 768", 768, 768),
    ("768 x 432 (16:9)", 768, 432),
    ("1024 x 576 (16:9)", 1024, 576),
    ("1280 x 720 (16:9)", 1280, 720),
    ("432 x 768 (9:16)", 432, 768),
    ("576 x 1024 (9:16)", 576, 1024),
    ("720 x 1280 (9:16)", 720, 1280),
    ("640 x 480 (4:3)", 640, 480),
    ("896 x 672 (4:3)", 896, 672),
    ("1152 x 864 (4:3)", 1152, 864),
    ("480 x 640 (3:4)", 480, 640),
    ("672 x 896 (3:4)", 672, 896),
    ("864 x 1152 (3:4)", 864, 1152),
)

# Seconds per step on an M5 Pro, 64 GB, int8, guidance 4:
#
#   megapixels          0.26   0.59   1.05
#   generate            2.18   4.44   8.31
#   edit, 1 reference   3.63      -   9.42
#   edit, 4 references  9.71      -      -
#
# Generate is close to linear in pixels (exponent 0.96). Guidance above 1 runs
# two passes: guidance 1 at 1 MP took 3.96. Edit pays for the reference tokens
# on top of the output, so it grows slower with the output size, and each
# reference adds cost this curve does not see. The page corrects the rate from
# the live steps. The first image took 2.6s beyond its steps.
GENERATE_ESTIMATE = Estimate(step_cost=8.3, exponent=1.0, overhead=3, overhead_per_image=True)
EDIT_ESTIMATE = Estimate(step_cost=9.4, exponent=0.7, overhead=3, overhead_per_image=True)

SIZE = ParamSpec(
    id="size",
    kind="choice",
    default="1024x1024",
    choices=(
        *(Choice(f"{width}x{height}", label) for label, width, height in SIZES),
        Choice(MATCH, "Match reference (about 1 MP)"),
    ),
)
# An edit keeps the shape of the image it changes, unless you pick a size.
EDIT_SIZE = replace(SIZE, default=MATCH)
STEPS = ParamSpec(id="steps", kind="number", default=25, minimum=1, maximum=50, integer=True, step=1)
GUIDANCE = ParamSpec(id="guidance", kind="number", default=4.0, minimum=1, maximum=10, step=0.5)
# The same rule as qwen21, through mflux's shared Config.init_time_step: the
# strength is the share of the schedule skipped, so higher stays closer.
STRENGTH = ParamSpec(id="strength", kind="number", default=0.4, minimum=0.05, maximum=1, step=0.05)

# Only the Look options that passed the flux2 test in PROMPTS.md. flux2 draws
# text it is given, so a named film stock came out printed on a film frame.
LOOKS = pick_looks(
    {
        "Medium": ("Film photo", "Watercolor", "3D render"),
        "Light": ("Studio", "Night with neon"),
        "Camera": ("Wide 24mm", "Top-down"),
        "Color": ("Vivid", "Black and white"),
        "Room for text": ("Left", "Top"),
    },
    sentences={"Black and white": "Black and white film photograph, strong grain, high contrast."},
)

GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, STEPS, GUIDANCE, STRENGTH),
    max_references=1,  # Flux2Klein.generate_image takes one image_path
    prompt_hint="Describe the image. Say what to show, not what to leave out.",
    estimate=GENERATE_ESTIMATE,
    looks=LOOKS,
    templates=GENERATE_TEMPLATES,
)
EDIT = ModeSpec(
    id="edit",
    label="Edit",
    params=(EDIT_SIZE, STEPS, GUIDANCE),
    min_references=1,
    max_references=MAX_REFERENCES,
    prompt_hint="For example: put a small yellow hat on the apple",
    prompt_required="An edit instruction is required.",
    estimate=EDIT_ESTIMATE,
    templates=EDIT_TEMPLATES,
)


def flux2_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="flux2", name="FLUX.2 klein 9B", badge=badge, modes=(GENERATE, EDIT), max_batch=MAX_BATCH
    )
