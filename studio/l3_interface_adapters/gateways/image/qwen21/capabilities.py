"""What the Qwen-Image-2.1 backend offers the page, and what its runs cost.

The controls are the family's and live in `qwen_image_controls`. What is here is
what this checkpoint decides for itself: its identity, its step count, and the
fits measured on its own weights.
"""

from studio.l1_entities.capabilities import Capabilities, Estimate
from studio.l3_interface_adapters.gateways.image.shared.qwen_image_controls import (
    MAX_BATCH,
    edit_estimate,
    edit_mode,
    generate_mode,
    steps_param,
)

# Cost, before you spend it. Measured 2026-10-05 on an M5 Pro, 64 GB, bf16, two
# points at each size 20 steps apart so the fixed cost and the per-step cost
# separate. The low point is 2 steps, not 1: mflux refuses a single step.
#
#   seconds per step   0.26 MP   0.59 MP   1.05 MP
#   generate            not re-measured; see below
#   edit, 1 reference     0.82      2.07      5.41
#
#   fixed cost            14.6s     15.9s     53.9s
#
# The edit figures are the in-process mflux engine, which replaced the diffusers
# child. That child's curve was 1.31, 3.77 and 9.90 s/step on the same tiers, so
# the swap is about twice as fast per step, and it peaks at 36 to 46 GB against
# the 38.7 GiB the child held.
#
# A least-squares power law through the three points gives 4.72 and 1.336, and it
# lands within 13% at the worst of them. The cost is superlinear in pixels because
# attention is quadratic in token count, which is what the exponent carries.
#
# **The generate half is measured too**, 2026-10-05, same method and machine. The
# first row is left out of the fit: it carries the model build, which the first run
# of a process pays and the rest do not.
#
#   seconds per step   0.26 MP   0.59 MP   1.05 MP
#   generate            (10.0s)     1.41      3.40     fixed cost 1.3s and 7.9s
#
# The pin moved to mflux 0.21.0 while this was measured, which added a text-prefix
# KV cache and a fused Metal kernel, so the pair is roughly half what it was: the
# old 6.1 and 1.55 predicted 2.73 s/step at 0.59 MP against 1.41 now.
GENERATE_STEP_COST = 3.15
GENERATE_STEP_EXPONENT = 1.53
EDIT_STEP_COST = 4.72
EDIT_STEP_EXPONENT = 1.336
# The fixed cost before the first step, which is the prompt and image encode. It is
# not flat: 14.6s and 15.9s at the two small tiers, 53.9s at 1.05 MP, and 70.8s for
# ten references at 0.59 MP. One number cannot follow a size and a reference count,
# so this sits between them and errs high. Measured 2026-10-05.
#
# Reference growth is the same problem. Going from one reference to two multiplies
# the step cost by 1.30, and one to ten only by 2.09, so the growth is sublinear and
# a single multiplier cannot hold both ends. 0.20 is fitted at two references, where
# a marked edit lives, because a mark rides as one more reference. It reads 8% short
# there and 34% long at ten. Measured 2026-10-05 at 0.59 MP.
REFERENCE_STEP_GROWTH = 0.20  # one more reference multiplies the step cost by 1 + this
GENERATE_OVERHEAD = 3  # per image; the model is already resident. Measured 1.3s at 0.59 MP and 7.9s at 1.05 MP
EDIT_OVERHEAD = 30

# 40 steps is this checkpoint's own setting, and its range is the span it was
# measured over. The Turbo checkpoint pins its count elsewhere, because its
# schedule has eight nodes and no other count is one it was distilled for.
STEPS = steps_param(default=40, minimum=1, maximum=100)

GENERATE_ESTIMATE = Estimate(GENERATE_STEP_COST, GENERATE_STEP_EXPONENT, GENERATE_OVERHEAD, overhead_per_image=True)
EDIT_ESTIMATE = edit_estimate(EDIT_STEP_COST, EDIT_STEP_EXPONENT, EDIT_OVERHEAD, REFERENCE_STEP_GROWTH)

GENERATE = generate_mode(STEPS, GENERATE_ESTIMATE, None)
EDIT = edit_mode(STEPS, EDIT_ESTIMATE)


def qwen21_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="qwen21",
        name="Qwen-Image-2.1",
        badge=badge,
        modes=(GENERATE, EDIT),
        max_batch=MAX_BATCH,
        description="Full quality: 40 steps. Edits with up to 10 references.",
    )
