"""The unmeasured controls offered by the official Qwen Turbo checkpoint."""

from studio.l1_entities.capabilities import Capabilities, Choice, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.qwen_image_sizes import EDIT_RESOLUTIONS, SIZES

MATCH = "match"
MAX_BATCH = 1

SIZE = ParamSpec(
    id="size",
    kind="choice",
    default="1024x1024",
    choices=(
        *(Choice(f"{width}x{height}", label) for label, width, height in SIZES),
        Choice(MATCH, "Match reference (about 1 MP)"),
    ),
)
STEPS = ParamSpec(id="steps", kind="number", default=8, minimum=8, maximum=8, integer=True, step=1)
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

GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, STEPS, STRENGTH),
    max_references=1,
    prompt_hint="Describe the image. Put any text you want rendered in quotes.",
    estimate=None,
)
EDIT = ModeSpec(
    id="edit",
    label="Edit",
    params=(RESOLUTION, STEPS),
    min_references=1,
    max_references=1,
    prompt_hint="For example: change the light to a warm evening glow",
    prompt_required="An edit instruction is required.",
    estimate=None,
)


def qwen21_turbo_capabilities(badge: str = "bf16") -> Capabilities:
    return Capabilities(
        backend_id="qwen21_turbo",
        name="Qwen-Image-2.1-Turbo",
        badge=badge,
        modes=(GENERATE, EDIT),
        max_batch=MAX_BATCH,
        description="Official 8-step checkpoint. Runtime and prompt aids await local validation.",
    )
