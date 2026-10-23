"""The official Turbo checkpoint: the family's controls, on the schedule it ships.

The controls are the family's and live in `qwen_image_controls`: the same Looks,
templates, sizes, reference limits, true CFG and region marking as Qwen-Image-2.1.
What is here is what this checkpoint decides for itself: its identity, its step
count, and the fits measured on its own weights.

The step count is not a preference. The checkpoint ships an eight-node sigma table
and `qwen21_turbo_schedule` samples it, so eight is the only count the engine
accepts, and the count is read from that module rather than typed again here.
"""

from studio.l1_entities.capabilities import Capabilities, Estimate
from studio.l3_interface_adapters.gateways.image.shared.qwen21_turbo_schedule import STEPS as SCHEDULE_STEPS
from studio.l3_interface_adapters.gateways.image.shared.qwen_image_controls import (
    MAX_BATCH,
    edit_estimate,
    edit_mode,
    generate_mode,
    steps_param,
)

# Measured 2026-10-16 on the M5 Pro with 64 GB and bf16 weights,
# on the checkpoint's own eight-node table. Two runs at each of three sizes (0.26,
# 0.59 and 1.05 MP) after a warmup. The step cost is fitted from the run's own step
# timestamps, which is the only measurement of it that the fixed cost cannot move,
# and the fixed cost is what is left of the wall clock.
#
#   seconds per step   0.26 MP   0.59 MP   1.05 MP     worst error of the fit
#   generate             0.52      1.27      2.69          6.3%
#   generate, 1 ref      0.62      1.48      2.85          1.2%   (five steps run at strength 0.4)
#   edit, 1 reference    0.71      1.94      3.78          5.5%
#
# The fixed cost is the prompt and reference encode, and it depends on whether the
# prompt is one the engine has already encoded. mflux keeps a text-prefix KV cache:
# the same prompt sent twice costs 0.90, 1.75 and 2.42s at the three sizes, and a
# prompt nobody has sent before costs 4.27, 5.44 and 6.51s. The higher reading is the
# one carried below, because a user typing a prompt is the ordinary case. A second
# session reproduced it: at 0.59 MP, 13 words took 16.27s of wall clock against 17.88s
# for 55, so length is worth about 1.6s of that and the encode is the rest.
#
# Against 45 real generate runs of this backend, whose prompts carry a Look sentence
# or a template, the estimate reads 1.45x low. That is the other session being slower
# per step than this fit, not the fit missing a term: its runs' own timings put the
# step cost about a fifth above what these numbers were measured at, and the same
# holds for the edit figure below.
#
# A reference adds no fixed cost worth a number of its own. The two shapes' fixed
# costs matched within 0.1s at every size, and a run at strength 1.0 denoises not at
# all and took 0.95, 1.79 and 2.90s, which is the same figure reached another way.
#
# Edit pays far more than generate, 12.0 to 36.9s, because it encodes its references
# at their own resolution. The value below is the mean over the three sizes, so it
# errs high at the small ones and low at the largest. The real edits this backend
# served at 0.39 and 0.59 MP imply about 15.5s against this 21.9, so the estimate
# reads about a third long there. The Qwen-Image-2.1 fit records the same compromise,
# for the same reason, and no single number can hold a cost that grows with the frame.
#
# The per-reference growth is the other place the model runs out of room. Ten
# references cost 94.4s at 0.59 MP against 31.3s for one, and the step cost only
# rises 2.13x between them; the rest of that is nine more encodes, which this
# record has nowhere else to put. 0.447 is the factor that matches the measured
# total, and it is deliberately the high reading.
#
# The run's own page replaces these numbers with what the device measured after the
# first run of a shape, so they are the first guess rather than the standing answer.
#
# One correction it makes is not measured here. A set negative prompt reads as two
# passes and doubles the estimate. That is right for generate, where guidance 2.5
# with a negative took 37.9s against 16.8s at guidance 1: 2.27x. It is high for
# edit, where cfg 2.5 took 36.8s against 26.6s, which is 1.38x, so an edit with a
# negative prompt is estimated about 45% long. The base model's record carries the
# same correction and the same reason.
GENERATE_ESTIMATE = Estimate(2.429, 1.173, 5.4, overhead_per_image=True)
GENERATE_REFERENCE_ESTIMATE = Estimate(
    2.679,
    1.097,
    5.4,
    overhead_per_image=True,
    strength_scales_steps=True,
)
EDIT_ESTIMATE = edit_estimate(3.463, 1.234, 21.9, 0.447)

STEPS = steps_param(default=SCHEDULE_STEPS, minimum=SCHEDULE_STEPS, maximum=SCHEDULE_STEPS)

GENERATE = generate_mode(STEPS, GENERATE_ESTIMATE, GENERATE_REFERENCE_ESTIMATE)
EDIT = edit_mode(STEPS, EDIT_ESTIMATE)


def qwen21_turbo_capabilities(badge: str = "bf16") -> Capabilities:
    return Capabilities(
        backend_id="qwen21_turbo",
        name="Qwen-Image-2.1-Turbo",
        badge=badge,
        modes=(GENERATE, EDIT),
        max_batch=MAX_BATCH,
        description="Official 8-step checkpoint. Its own sampling schedule.",
    )
