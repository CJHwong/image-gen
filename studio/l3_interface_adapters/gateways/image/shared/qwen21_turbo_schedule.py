"""Sample the official Turbo checkpoint on the sigma table it ships.

mflux builds a plain linear table for this checkpoint and never reads the
`sample_sigmas` it carries. `grep -rn sample_sigmas` over the mflux package finds
nothing, and `LinearScheduler` is `linspace(1, 1/steps, steps)` plus a trailing
zero, with the shift skipped because `requires_sigma_shift` is false for this
checkpoint. The model card says the opposite of what that does: "The recommended
8-step sampling schedule is saved with the checkpoint and loaded automatically.
Setting `num_inference_steps` alone does not override it." So the studio was
sampling a distilled checkpoint off the schedule it was distilled for.

Measured 2026-10-16 on the M5 Pro, one prompt and two seeds at 768 x 768,
the shipped table against the linear one: RMS 26.3 and 35.3 between the pairs, as
large as the gap between 8 and 40 steps, with the linear table 2.5 to 3.1 higher
on edge energy and the shipped one up to 3.6x on clipped highlights. Two seeds and
one prompt say which way a schedule moves a picture, not which is better. The
shipped table is the publisher's own and the one they evaluated.

The table is the eight values in the checkpoint's `model_index.json`, kept here as
a constant the way mflux keeps the viggle nodes, because a scheduler is built from
a name and a Config and is given no model directory. `test_qwen21_turbo_live.py`
compares this constant against the checkpoint itself, so a republished table
cannot drift away from it unnoticed.

Eight nodes means eight steps and no other count, because the loop walks
consecutive nodes. `ViggleTurboScheduler` refuses a different count the same way,
and the turbo capability record pins `steps` at 8 so the page cannot ask for one.

This sits beside the backends rather than inside one, because a backend may not
import another backend. `viggle_schedule`, `mflux_runtime` and `qwen_image_sizes`
are here for the same reason.
"""

from contextlib import contextmanager

SCHEDULER_NAME = "qwen_turbo_official"

# The checkpoint's own `sample_sigmas`, verbatim and in order. The last node is
# 0.41, so the final step is a large jump by design: five short steps and then one
# long one is what this distillation does.
SIGMA_NODES = (1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568)
STEPS = len(SIGMA_NODES)


def _scheduler_class():
    import mlx.core as mx
    from mflux.models.common.schedulers.base_scheduler import BaseScheduler

    class OfficialTurboScheduler(BaseScheduler):
        """The checkpoint's nodes, unshifted, with the terminal zero mflux expects.

        The shift is skipped on purpose. The official scheduler's config carries
        `shift: 1.0` with dynamic shifting off, which is the identity, and
        `official_turbo_model_config` turns the resolution-dependent shift and the
        terminal rescale off for this checkpoint already.
        """

        SIGMA_NODES = SIGMA_NODES

        def __init__(self, config):
            self.config = config
            steps = config.num_inference_steps
            if steps != len(self.SIGMA_NODES):
                raise ValueError(
                    f"the official Turbo table samples on its {len(self.SIGMA_NODES)} nodes, "
                    f"but num_inference_steps is {steps}. Use --steps {len(self.SIGMA_NODES)}."
                )
            self._sigmas = mx.concatenate([mx.array(list(self.SIGMA_NODES), dtype=mx.float32), mx.zeros(1)])
            self._timesteps = mx.arange(steps, dtype=mx.float32)

        @property
        def sigmas(self) -> mx.array:
            return self._sigmas

        @property
        def timesteps(self) -> mx.array:
            return self._timesteps

        def step(self, noise: mx.array, timestep: int, latents: mx.array, **kwargs) -> mx.array:
            dt = (self._sigmas[timestep + 1] - self._sigmas[timestep]).astype(latents.dtype)
            return latents + noise.astype(latents.dtype) * dt

    return OfficialTurboScheduler


def register_schedule() -> None:
    """Make the schedule known to mflux under its name.

    The gateway calls this when a run starts, which is the last moment it can: mflux
    resolves the name when it builds a `Config`, and building a backend must not
    import mflux, because the stub builds every backend on hosts that cannot run a
    model at all. Not run at import either, so a unit test can stub the engine.

    Registering twice is harmless, because mflux's registry is a dictionary
    assignment, so this needs no guard.
    """
    from mflux.models.common.schedulers import register_contrib

    register_contrib(_scheduler_class(), SCHEDULER_NAME)


@contextmanager
def official_turbo_schedule():
    """Make Config's own default this schedule for the length of the block.

    The edit variant's `generate_image` takes no scheduler argument and builds its
    `Config` without one, so its default is the only way in. Same patch, and same
    reason, as `viggle_schedule`.
    """
    from mflux.models.common.config.config import Config

    register_schedule()
    original = Config.__init__

    def with_official_turbo(self, *args, **kwargs):
        kwargs.setdefault("scheduler", SCHEDULER_NAME)
        original(self, *args, **kwargs)

    Config.__init__ = with_official_turbo
    try:
        yield
    finally:
        Config.__init__ = original
