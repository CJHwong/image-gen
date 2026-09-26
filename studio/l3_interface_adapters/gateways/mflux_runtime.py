"""What every mflux model in this server shares: the step hook and the buffer release."""

import gc
from collections.abc import Callable
from contextlib import contextmanager

from studio.l1_entities.errors import Cancelled


class StepHook:
    """mflux's per-step hook: the only way into a generation already running.

    Register it once on the model, not once per generation, because
    CallbackRegistry.register appends and never dedups. `watch` points it at
    the run in flight.

    Cancel raises from here. mflux's loop catches only KeyboardInterrupt, so a
    different exception propagates straight out of generate_image: it stops at
    the current step rather than at the end of the image.

    This hook could also decode the half-finished latents and show a live
    preview. It does not, and that is deliberate. For Qwen-Image-2.1 a preview
    is a full decode of a 64-channel VAE at 16x compression: 1.40s at 512, 7.42s
    at 768 and 8.05s at 1024. The wall clock pays more than that, because the
    decode's allocations disturb the steps that follow. At 1024, 40 steps, two
    runs each:

        no previews      157.4s  154.9s
        every 20 steps   187.1s  176.0s
        every  5 steps   248.3s  295.6s

    One preview at 1024 costs about 25s. That is a tax, not a feature.

    Cancel lands here, at the top of a step. This engine runs inside the server's own
    process, so there is nothing to kill and the only place it can look is a step: a
    cancel during the load or the encode waits for the first one. A child engine's
    cancel kills the child at once, because that engine can be killed. The page says
    when the stop lands rather than that it has already landed.
    """

    def __init__(self):
        self._on_step = None
        self._should_stop = None
        self._total = 0

    @contextmanager
    def watch(self, on_step: Callable[[int, int], None], should_stop: Callable[[], bool], total: int):
        self._on_step, self._should_stop, self._total = on_step, should_stop, total
        try:
            yield
        finally:
            self._on_step = self._should_stop = None

    def call_in_loop(self, t, seed, prompt, latents, config, time_steps):
        on_step, should_stop = self._on_step, self._should_stop
        if on_step is None or should_stop is None:
            return
        # With a starting image, mflux runs only range(init_time_step, steps):
        # the strength skips the start of the schedule. Count the steps that
        # run, or the first one shows as 42% at strength 0.4.
        start = config.init_time_step if config is not None else 0
        total = config.num_inference_steps if config is not None else self._total
        if should_stop():
            raise Cancelled(f"stopped at step {t + 1 - start}")
        on_step(t + 1 - start, total - start)


def release_mlx_buffers() -> None:
    """Hand MLX's reuse pool back after each generation.

    MLX keeps freed buffers to reuse. A CLI run exits and the OS takes them
    back; a resident server just holds them. Measured at 1024: 22.42 GB held
    between generations without this, 0.00 GB with it. Nothing accumulates
    either way, so it is not a leak. It is headroom given back.
    """
    import mlx.core as mx

    gc.collect()
    mx.clear_cache()
