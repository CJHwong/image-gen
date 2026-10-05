"""What the Viggle Turbo backend offers the page, and the limits the core checks.

Viggle Turbo is Qwen-Image-2.1 sampled on a distilled six-step schedule, so the
grid, the reference limits and the model itself are the base model's. What
changes is what the page may offer.

The distillation was trained to run without classifier-free guidance, so this
backend declares no guidance, no negative prompt and no cfg. And mflux's
`ViggleTurboScheduler` raises on any step count but six, before the model loads,
so that field is not a default the user may move.

No Looks and no templates. ARCHITECTURE.md says to leave them out until they are
tested on this model, and nobody has tested them on the distilled schedule.
Region marking is out for the same reason: the mark's bounding power was measured
on the 40-step base, not here.
"""

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.qwen_image_sizes import EDIT_MATCH_CAP, EDIT_RESOLUTIONS, SIZES

MATCH = "match"
MAX_BATCH = 4
MAX_REFERENCES = 10

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

# The base model's numbers, which the adapter does not change: the same
# transformer runs, with Viggle's LoRA on top. They are a placeholder until the
# first real six-step run on this machine, and the page corrects the rate from
# its own steps anyway. The table they came from is in
# gateways/qwen21/capabilities.py beside the constants.
GENERATE_ESTIMATE = Estimate(6.1, 1.55, 3, overhead_per_image=True)
EDIT_ESTIMATE = Estimate(4.72, 1.336, 30, overhead_per_image=True, match_cap=EDIT_MATCH_CAP)

GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, STEPS, STRENGTH),
    max_references=1,
    prompt_hint="Describe the image. Put any text you want rendered in quotes.",
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
    estimate=EDIT_ESTIMATE,
)


def viggle_turbo_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="viggle_turbo",
        name="Viggle Turbo",
        badge=badge,
        modes=(GENERATE, EDIT),
        max_batch=MAX_BATCH,
    )
