"""What the Viggle Turbo backend offers the page, and the limits the core checks.

Viggle Turbo is Qwen-Image-2.1 sampled on a distilled six-step schedule, so the
grid, the reference limits and the model itself are the base model's. What
changes is what the page may offer.

The distillation was trained to run without classifier-free guidance, so this
backend declares no guidance, no negative prompt and no cfg. And mflux's
`ViggleTurboScheduler` raises on any step count but six, before the model loads,
so that field is not a default the user may move.

No Looks and no templates were inherited. They were sampled on this model's own
schedule, and what survived is declared below. An option chosen on the 40-step
base is not evidence on a distilled schedule, and every option here was run next
to the bare prompt and did what its sentence says.

Region marking is out because six steps has not been established to hold a mark, and
the measurements contradict each other. On the base model's own circle fixture, three
seeds at six steps scored 21.3x, 26.5x and 21.3x, against 25.3x, 35.1x and 22.6x for
the 40-step base: comparable. A repeat of the same edit reproduced bit-identically. An
earlier harness, on a scene built to match, scored the same edits at 2.2x and 2.5x, and
also reproduced bit-identically. Every input that can be named was checked, including
the scene, seed, prompt, references, options and step count, and the difference was
not found. Until it is, the tool stays out: the safe side of an unresolved measurement
is not offering it.
"""

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.prompt_aids import pick_looks, pick_templates
from studio.l3_interface_adapters.gateways.qwen_image_sizes import EDIT_MATCH_CAP, EDIT_RESOLUTIONS, SIZES

MATCH = "match"
MAX_BATCH = 4
MAX_REFERENCES = 10

# What the six-step sample kept, and nothing else. Every option here ran on this
# model's own schedule, at 768 x 768 and seed 1234, next to the bare prompt, and
# changed the image the way its sentence says. The options left out were not
# sampled on this model at all, so they stay out until someone runs them.
# PROMPTS.md holds the tables, the fixture of each row, and the limits: one seed,
# and no negative prompt on this backend to carry an avoid part.
LOOKS = pick_looks(
    {
        "Medium": ("Documentary", "Watercolor", "Skeleton"),
        "Film": ("Portra 400", "Black and white"),
        "Color": ("Warm", "Vivid"),
        "Light": ("Soft window light", "Golden hour", "Night with neon"),
        "Camera": ("Close-up 85mm", "Wide 24mm", "Top-down"),
        "Room for text": ("Left", "Top"),
        "Realism": ("Real person",),
        "Portrait": ("Over the shoulder", "Candid glance"),
    }
)
# The whole of each mode's templates, less Mark a region, which needs the draw
# tool this backend does not offer.
GENERATE_TEMPLATES = pick_templates(
    (
        "Portrait photo",
        "Product shot",
        "Landscape",
        "Poster with text",
        "Illustration",
        "Deadpan absurdity",
        "Banner",
    )
)
EDIT_TEMPLATES = pick_templates(
    (
        "Change a color or material",
        "Replace the background",
        "Add text",
        "Alternate reality",
        "Add an object",
        "Turn into a skeleton",
        "Turn into a pose figure",
    )
)

# Six, and only six. Both bounds are the same number because the schedule is not
# a preference: it is the set of sigma nodes the student was trained on.
STEPS = ParamSpec(id="steps", kind="number", default=6, minimum=6, maximum=6, integer=True, step=1)

SIZE = ParamSpec(
    id="size",
    kind="choice",
    default="1024x1024",
    choices=(
        *(Choice(f"{width}x{height}", label) for label, width, height in SIZES),
        Choice(MATCH, "Match reference (about 1 MP)"),
    ),
)
# The scheduler's own docstring: strength below 1 starts the loop at the node
# int(6 * strength) on the shifted table, so the base model's rule still holds.
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

# Measured 2026-10-05 on the M5 Pro, six steps, one reference, and set against the
# base model's constants. Viggle can only run six steps, so the fixed cost cannot be
# separated from the per-step cost the way the base model's was; what these say is
# whether that pair still predicts a six-step run.
#
#   measured total   0.26 MP   0.59 MP   1.05 MP
#   generate            5.9s      9.9s     23.6s
#   edit               18.8s     19.3s     37.3s
#
# Generate is the base model's pair within 15% at all three sizes, so it keeps them.
# Edit does not: the base model's overhead of 30 is fitted from two-step and
# twenty-two-step runs and dominates a six-step one, predicting 35, 44 and 60
# seconds against those. The same per-step curve with this backend's own overhead of
# 10 predicts 15, 24 and 40, inside 24% at all three.
GENERATE_ESTIMATE = Estimate(3.15, 1.53, 3, overhead_per_image=True)
EDIT_ESTIMATE = Estimate(4.72, 1.336, 10, overhead_per_image=True, match_cap=EDIT_MATCH_CAP)

GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, STEPS, STRENGTH),
    max_references=1,
    prompt_hint="Describe the image. Put any text you want rendered in quotes.",
    looks=LOOKS,
    templates=GENERATE_TEMPLATES,
    estimate=GENERATE_ESTIMATE,
)
EDIT = ModeSpec(
    id="edit",
    label="Edit",
    params=(RESOLUTION, STEPS),
    min_references=1,
    max_references=MAX_REFERENCES,
    prompt_hint="For example: make it night, with the lights on",
    prompt_required="An edit instruction is required.",
    templates=EDIT_TEMPLATES,
    estimate=EDIT_ESTIMATE,
)


def viggle_turbo_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="viggle_turbo",
        name="Qwen-Image-2.1-viggle-turbo",
        badge=badge,
        modes=(GENERATE, EDIT),
        max_batch=MAX_BATCH,
        description="Viggle's distillation: six steps, no guidance.",
    )
