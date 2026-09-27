from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l3_interface_adapters.gateways.mflux_runtime import StepHook, release_mlx_buffers
from tests.support.heavy import heavy_modules


class Config:
    """The two fields of mflux's config that the step count comes from."""

    def __init__(self, init_time_step, num_inference_steps):
        self.init_time_step = init_time_step
        self.num_inference_steps = num_inference_steps


class Recorder:
    def __init__(self, stop=False):
        self.steps = []
        self.stop = stop

    def on_step(self, step, total):
        self.steps.append((step, total))

    def should_stop(self):
        return self.stop


def test_a_step_no_run_is_watching_is_ignored():
    # The hook is registered on the model once, for the model's whole life, so it
    # also fires for a generation no run is watching. Reporting it would send a
    # finished run's steps into the next run's page.
    hook = StepHook()
    hook.call_in_loop(0, 1, "a cat", None, None, None)
    hook.call_in_loop(1, 1, "a cat", None, None, None)


def test_a_step_is_counted_from_the_first_step_the_engine_runs():
    # With a starting image mflux runs range(init_time_step, steps): the strength
    # skips the start of the schedule. Counting from 0 shows the first step as
    # 42% at strength 0.4.
    recorder = Recorder()
    hook = StepHook()
    with hook.watch(recorder.on_step, recorder.should_stop, 25):
        hook.call_in_loop(10, 1, "a cat", None, Config(init_time_step=10, num_inference_steps=25), None)
        hook.call_in_loop(11, 1, "a cat", None, Config(init_time_step=10, num_inference_steps=25), None)
    assert recorder.steps == [(1, 15), (2, 15)]


def test_a_step_without_a_config_counts_the_whole_schedule():
    recorder = Recorder()
    hook = StepHook()
    with hook.watch(recorder.on_step, recorder.should_stop, 4):
        hook.call_in_loop(0, 1, "a cat", None, None, None)
    assert recorder.steps == [(1, 4)]


def test_a_cancel_raises_at_the_mflux_step_it_lands_on():
    # mflux's loop catches only KeyboardInterrupt, so this exception leaves
    # generate_image at the current step rather than at the end of the image.
    recorder = Recorder(stop=True)
    hook = StepHook()
    with hook.watch(recorder.on_step, recorder.should_stop, 25):
        with pytest.raises(Cancelled, match="stopped at step 5"):
            hook.call_in_loop(4, 1, "a cat", None, None, None)
    assert recorder.steps == []


def test_the_watch_ends_with_the_run_it_was_opened_for():
    recorder = Recorder()
    hook = StepHook()
    with hook.watch(recorder.on_step, recorder.should_stop, 4):
        pass
    hook.call_in_loop(0, 1, "a cat", None, None, None)
    assert recorder.steps == []


def test_the_mlx_reuse_pool_is_handed_back():
    # A CLI run exits and the OS takes the buffers back; a resident server holds
    # them. Measured at 1024: 22.42 GB held between generations without this,
    # 0.00 GB with it.
    clear_cache = Mock()
    with heavy_modules({"mlx.core": {"clear_cache": clear_cache}}):
        release_mlx_buffers()
    clear_cache.assert_called_once_with()
