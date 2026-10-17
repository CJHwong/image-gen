"""The controls every Qwen-Image-2.1 checkpoint offers, and the limits the core checks.

The two backends that drive this model family run the same mflux engines, so they
offer the same form: the same sizes, the same reference limits and steps, the same
Look rows and templates, true CFG on both modes, and region marking on an edit.
Only three things differ between them, and each stays in its own capabilities
module: its identity, the step count its schedule samples, and the cost fits
measured on its own weights.

This sits beside the backends rather than inside one, because a backend may not
import another backend. `qwen_image_sizes`, `prompt_aids` and `mflux_runtime` are
here for the same reason.

Everything measured in the comments below was measured on Qwen-Image-2.1, on
2026-10-05 and 2026-10-10, before the official Turbo checkpoint existed here. That
covers the behaviour as well as the figures, and the reason is not only the dates:
the edit Look verdicts and the mark's containment were taken at 20 steps, and this
repo's own tables show both move with the schedule, from 28.8x at 20 steps to 21.0x
at Viggle's six. So none of it is a claim about Turbo. What Turbo measures for
itself is its step count, its cost fits, and the aid verdicts in PROMPTS.md.
"""

from studio.l1_entities.capabilities import Choice, Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.prompt_aids import (
    EDIT_LOOKS,
    EDIT_TEMPLATES,
    GENERATE_LOOKS,
    GENERATE_TEMPLATES,
)
from studio.l3_interface_adapters.gateways.qwen_image_sizes import (
    EDIT_MATCH_CAP,
    EDIT_RESOLUTIONS,
    SIZES,
)

MATCH = "match"
MAX_REFERENCES = 10
MAX_BATCH = 4

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
# strength)). Measured on Qwen-Image-2.1, RMS distance from the reference, one
# pear at 8 steps: 17.1 at 0.15, 4.0 at 0.55, 2.5 at 0.85, and 74.5 with no
# reference. Every strength stays close to the reference, so drop the reference
# when the prompt should win.
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
NEGATIVE = ParamSpec(id="negative", kind="text", default="")
CFG = ParamSpec(id="cfg", kind="number", default=1.0, minimum=1, maximum=10, step=0.5, with_negative=2.5)


def steps_param(default: int, minimum: int, maximum: int) -> ParamSpec:
    """The step count, which is the one control a schedule decides for itself."""
    return ParamSpec(id="steps", kind="number", default=default, minimum=minimum, maximum=maximum, integer=True, step=1)


def generate_mode(steps: ParamSpec, estimate: Estimate, reference_estimate: Estimate | None) -> ModeSpec:
    """A generate mode. `reference_estimate` is None where a checkpoint has no fit
    for a run that starts from a reference, which Qwen-Image-2.1 does not."""
    return ModeSpec(
        id="generate",
        label="Generate",
        params=(SIZE, steps, GUIDANCE, STRENGTH, NEGATIVE),
        max_references=1,  # mflux's generate_image takes one image_path
        prompt_hint="Describe the image. Put any text you want rendered in quotes.",
        looks=GENERATE_LOOKS,
        templates=GENERATE_TEMPLATES,
        estimate=estimate,
        reference_estimate=reference_estimate,
    )


def edit_mode(steps: ParamSpec, estimate: Estimate) -> ModeSpec:
    return ModeSpec(
        id="edit",
        label="Edit",
        params=(RESOLUTION, steps, CFG, NEGATIVE),
        min_references=1,
        max_references=MAX_REFERENCES,
        prompt_hint="For example: make it night, with the lights on",
        prompt_required="An edit instruction is required.",
        templates=EDIT_TEMPLATES,
        # The edit Look, all six rows and every option of them, because Qwen-Image-2.1 is
        # the model they were sampled on: 18 options, 15 that landed and 3 that did not, on
        # 2026-10-10. PROMPTS.md holds the table. On that model a whole-frame option lands:
        # it keeps the rest of the picture and applies the look it was asked for, and the
        # composition held in every sample. What the mark does not do, also on that model, is
        # bound a retouch, so a picked Retouch option reaches past the drawn area. PROMPTS.md
        # records that too, and holds this checkpoint's own verdicts for the same 15 options.
        looks=EDIT_LOOKS,
        estimate=estimate,
        # Measured on Qwen-Image-2.1, 2026-10-05, on the in-process mflux engine, one seed
        # and 20 steps, on a drawn shape whose edge the mark matched: the change landed 15.8x
        # more inside the marked area than outside it, and the rest of the frame moved by 4.3
        # of 255. PROMPTS.md keys this measurement by engine, scene and steps, and it moves
        # with all three: 3.1x, 15.8x and 28.8x across three scenes at 20 steps, and 2.2x,
        # 11.9x and 21.0x on the same scenes at Viggle's six. The official Turbo checkpoint
        # has a row of its own, measured 2026-10-16 at its eight steps on rebuilt scenes:
        # 28.6x on the drawn circle against the base model's 28.8x, so this control is
        # offered there on a figure of its own rather than on another model's.
        #
        # The engine swap is a wash on this, not a win. On the fixture the old figure came
        # from, the diffusers child this replaced read 37.5x against 28.8x here, and on a
        # mark over a uniform surface, where only the mark can bound the change, 2.4x
        # against 3.1x. One seed on one fixture settles neither direction, so neither claim
        # is made. PROMPTS.md holds the tables and their limits.
        region_marking=True,
        # Each reference is edited on its own through the same single-image call the mode
        # was measured with, so a batch adds runs and not a new engine path.
        each_reference=True,
    )


def edit_estimate(step_cost: float, exponent: float, overhead: float, per_reference: float) -> Estimate:
    """The edit fit: an edit pays the encode of every reference it is given."""
    return Estimate(
        step_cost,
        exponent,
        overhead,
        # Every image of a batch is its own run, so each one pays the encode before
        # its first step. The model stays resident, so there is no pipeline build
        # to count.
        overhead_per_image=True,
        match_cap=EDIT_MATCH_CAP,
        per_reference=per_reference,
    )
