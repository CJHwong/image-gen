from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import (
    StepHook,
    lora_kwargs,
    official_turbo_model_config,
    release_mlx_buffers,
)
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
    with (
        hook.watch(recorder.on_step, recorder.should_stop, 25),
        pytest.raises(Cancelled, match="stopped at step 5"),
    ):
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


def test_a_lora_is_passed_unmerged_and_a_backend_without_one_passes_nothing():
    """`bake_lora=False` is not a preference: mflux merges an adapter into the base
    weights by default, and the card for the one this server loads says merging into
    bf16 drops about 30 percent of the update."""
    assert lora_kwargs(None) == {}
    assert lora_kwargs("/adapters/turbo.safetensors") == {
        "lora_paths": ["/adapters/turbo.safetensors"],
        "lora_scales": [1.0],
        "bake_lora": False,
    }
    assert lora_kwargs("/adapters/turbo.safetensors", 0.5)["lora_scales"] == [0.5]


def test_official_turbo_uses_a_copy_of_the_model_config_without_dynamic_shift():
    from mflux.models.common.config.model_config import ModelConfig

    base_config = ModelConfig.qwen_image_21()
    turbo_config = official_turbo_model_config()

    assert turbo_config is not base_config
    assert (turbo_config.requires_sigma_shift, turbo_config.sigma_shift_terminal) == (False, None)
    assert (base_config.requires_sigma_shift, base_config.sigma_shift_terminal) == (True, 0.02)


@pytest.mark.parametrize("recommended", [32 * 1024**3, 60 * 1024**3])
@pytest.mark.parametrize("failure", [None, RuntimeError, Cancelled])
@pytest.mark.parametrize("sync_fails", [False, True])
def test_active_memory_is_bounded_and_restores_the_previous_limit(recommended, failure, sync_fails):
    from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import active_mlx_memory

    events = []
    previous = 12345

    def wired(value):
        events.append(("wired", value))
        return previous

    def synchronize():
        events.append(("synchronize",))
        if sync_fails:
            raise RuntimeError("synchronize failed")

    with heavy_modules(
        {
            "mlx.core": {
                "device_info": lambda: {"memory_size": 64 * 1024**3, "max_recommended_working_set_size": recommended},
                "set_wired_limit": wired,
                "synchronize": synchronize,
            }
        }
    ):

        def run():
            with active_mlx_memory():
                events.append(("engine",))
                if failure:
                    raise failure("engine stopped")

        if failure or sync_fails:
            with pytest.raises(RuntimeError if sync_fails else failure):
                run()
        else:
            run()

    assert events == [
        ("wired", min(recommended, 48 * 1024**3)),
        ("engine",),
        ("synchronize",),
        ("wired", previous),
    ]
