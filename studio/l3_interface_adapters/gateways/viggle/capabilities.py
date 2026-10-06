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

Region marking is offered, and the tool's own measurement is what decided it. A six-step
mark scored 21 to 26x on one scene and 2.2 to 2.5x on another, both reproducing
bit-identically, and the two scenes were believed to match. Measured again on 2026-10-06
through one metric, one seed and one code path: the high figure is a mark matching a
circle's own edge and the low one is a mark over a uniform surface. Six steps holds a
mark as well as forty does where there is an edge to hold it, 21.0x against 28.8x, and
neither engine bounds a mark on a surface with no edge, 2.2x against 3.1x. PROMPTS.md
holds both tables and the three scenes.

That is the bar this repo uses for a prompt aid, and the mark clears it on this schedule
rather than by inheritance: those runs used the sentence the page itself writes, including
the mark's palette colour. The page's own path was run on this backend on 2026-10-06,
three marks drawn on a circle it had drawn: the run whose mark followed the object's edge
scored 25.8x against the engine's 21.0x on the same scene. What is not measured here is
the palette leaking on a loose hand-drawn region, which PROMPTS.md records for the base
model.
"""

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.prompt_aids import pick_looks, pick_templates
from studio.l3_interface_adapters.gateways.qwen_image_sizes import EDIT_MATCH_CAP, EDIT_RESOLUTIONS, SIZES

MATCH = "match"
MAX_BATCH = 4
MAX_REFERENCES = 10

# Everything the six-step sample kept: the options it ran and that did what their
# sentence says, which is every option in the shared rows but Deep focus. Each one ran
# on this model's own schedule, at 768 x 768 and seed 1234, next to the bare prompt.
# Deep focus was the one that did not: run at three seeds, it changed nothing at one and
# changed the framing and the background content at the other two, never the depth of
# field its sentence names. PROMPTS.md holds the tables, the fixture of each row, and the
# limits: one seed unless noted, and no negative prompt on this backend to carry an avoid
# part.
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
# The whole of each mode's templates: seven for generate, and eight for edit, which
# includes Mark a region because the mark cleared this schedule's own measurement.
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
        "Mark a region",
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
# Generate had no measurement of its own until 2026-10-06, when the estimate the page
# shows was checked against real runs. The first check that day, at about 01:00, read
# 8.0s, 27.8s and 68.7s and was taken as proof that the pair here was about two and a
# half times fast. It was not. Measured again the same day at 11:25, GPU free, one job
# at a time, two passes of the same six steps at seed 1234 on the cat fixture:
#
#   measured total   0.26 MP      0.59 MP      1.05 MP
#   generate        4.9s, 6.1s   10.3s, 9.9s   23.9s, 23.5s
#
# The pair predicts 5.4s, 11.4s and 23.4s, which against the means of 5.5s, 10.1s and
# 23.7s is 13% high at the middle tier and within 2% at the other two. Six runs with
# that spread do not justify constants of this model's own, so the base model's pair
# stands and the pair that replaced it is gone.
#
# The same run does not have one time on this machine. Thirty-six of them at 1024 x 1024
# back to back, measured at 11:33, took between 20.0s and 51.6s, median 30.7s: the first
# 27 averaged 33.7s and the last 9 averaged 21.4s, which is the figure above again. The
# load average recorded beside each run explains only part of that spread, with a
# correlation of 0.56: the two highest loads gave the two slowest runs, and one run took
# 45.2s at load 1.71. So most of the spread is inside the machine, and I did not
# instrument which part of it. That pass repeated one prompt, which costs no rebuild
# after the first image, so the spread above is not that. A new prompt each time pays
# one, and that is a separate thing with its own cause and its own fix: the aid sample
# at 12:06 the same day, 768 x 768 at load 0.98, ran 10.9s, then 20.2s, then 25.6s, and
# each image after the first rebuilt the model over a live copy of itself. Dropping that
# copy first took the arm from 21.5s an image to 14.8s, both measured in one process.
# The 8.0s, 27.8s and 68.7s check read the slow end of the spread above as the machine's
# speed, which would have promised about three times the time an idle machine gives. The
# idle figure is the one this pair is for: the page shows the estimate before a run and
# learns this device's own rate from the run itself, so a machine at the slow end
# corrects the page within one run.
GENERATE_ESTIMATE = Estimate(3.15, 1.53, 3, overhead_per_image=True)
# Edit does not: the base model's overhead of 30 is fitted from two-step and
# twenty-two-step runs and dominates a six-step one, predicting 35, 44 and 60
# seconds against those. The same per-step curve with this backend's own overhead of
# 10 predicts 15, 24 and 40, inside 24% at all three. Measured again 2026-10-06 at
# 0.59 MP: two edits took 20.2s and 26.3s against that predicted 24.0s, so the pair
# holds and the 19.3s above is confirmed rather than inherited.
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
    region_marking=True,
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
