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

Region marking is out, and what kept it out turned out to be two scenes rather than a
contradiction. A six-step mark scored 21 to 26x on one and 2.2 to 2.5x on another, both
reproducing bit-identically, and the scenes were believed to match. Measured again on
2026-10-06 through one metric, one seed and one code path: the high figure is a mark
matching a circle's own edge and the low one is a mark over a uniform surface. Six steps
holds a mark as well as forty does where there is an edge to hold it, 21.0x against 28.8x,
and neither engine bounds a mark on a surface with no edge, 2.2x against 3.1x. PROMPTS.md
holds both tables and the three scenes.

So the engine is not the reason. The tool's wording, its brush and its palette were tested
on the 40-step base and never on this schedule, and the rule for every prompt aid here is
the same: it is offered once something has run it on this model. Offering a mark is
therefore a decision to test it, not a port to finish.
"""

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.prompt_aids import pick_looks, pick_templates
from studio.l3_interface_adapters.gateways.qwen_image_sizes import EDIT_MATCH_CAP, EDIT_RESOLUTIONS, SIZES

MATCH = "match"
MAX_BATCH = 4
MAX_REFERENCES = 10

# Everything the six-step sample kept: the options it ran and that did what their
# sentence says, which is now every option in the shared rows but Deep focus. Each one
# ran on this model's own schedule, at 768 x 768 and seed 1234, next to the bare
# prompt. Deep focus was the one that did not visibly work: its image is the bare
# prompt's close-up with the background still blurred, so it is not offered here.
# PROMPTS.md holds the tables, the fixture of each row, and the limits: one seed, and
# no negative prompt on this backend to carry an avoid part.
LOOKS = pick_looks(
    {
        "Medium": ("Documentary", "Phone snapshot", "Watercolor", "Ink drawing", "3D render", "Skeleton"),
        "Film": ("Portra 400", "Fuji 400H", "Ektachrome", "Black and white"),
        "Color": ("Warm", "Cool", "Muted", "Vivid"),
        "Light": ("Soft window light", "Golden hour", "Studio", "Overcast", "Night with neon"),
        "Camera": ("Close-up 85mm", "Wide 24mm", "Top-down", "Low angle", "Telephoto"),
        "Room for text": ("Left", "Right", "Top"),
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
#   edit, measured 2026-10-05   0.26 MP   0.59 MP   1.05 MP
#                               18.8s     19.3s     37.3s
#
# Generate was re-measured on 2026-10-06, because the figures above did not hold when
# the estimate the page shows was checked against real runs. Two passes, six runs at
# each tier, all six steps at seed 1234 on the cat fixture:
#
#   measured total        0.26 MP           0.59 MP                     1.05 MP
#   generate           8.0s, 8.1s   21.8 24.8 24.8 30.7 31.3 41.1   56.4 65.7 67.6 69.7 73.7 79.3
#
# The per-image time drifts inside a pass, with nothing changed between the runs: 768
# took 21.8s and later 41.1s, and the second pass, which interleaved the sizes, held
# 24.8s twice and then 30.7s. So the medians are what is fitted and the spread is
# quoted rather than smoothed away: 8.0s, 27.8s, 68.7s.
#
# Six steps is the only count this model takes, so a fixed cost cannot be separated from
# a per-step cost here. With the base model's exponent, which the measured 768-to-1024
# ratio of 2.5 supports, one constant fits all three tiers and needs no separate fixed
# cost:
#
#   predicted   8.1s     28.0s     67.2s
#   measured    8.0s     27.8s     68.7s
#
# The pair that was here predicted 5.4s, 11.4s and 23.4s at those tiers, so it read the
# middle and large tiers about two and a half times fast. The edit pair stays as it
# was: its 19.3s at 0.59 MP was reproduced at 20.6s over seven real edits.
GENERATE_ESTIMATE = Estimate(10.4, 1.53, 0, overhead_per_image=True)
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
