"""The Turbo scheduler: its table, its refusal, and the edit-path patch.

mflux has no scheduler for this checkpoint's own table, so this module both
registers one and, because the edit variant cannot select a scheduler, patches
`Config`'s default for the length of one call. The second half carries the same
upstream tripwire as `viggle_schedule`, which lives in `test_viggle_schedule.py`.

Nothing here imports mflux or mlx for real. Both are stubbed, which is what the
deferred imports in the module make possible.
"""

from itertools import pairwise

import pytest

from studio.l3_interface_adapters.gateways.image.shared.qwen21_turbo_schedule import (
    SCHEDULER_NAME,
    SIGMA_NODES,
    STEPS,
    official_turbo_schedule,
    register_schedule,
)
from tests.support.heavy import heavy_modules

SCHEDULERS = "mflux.models.common.schedulers"
BASE_SCHEDULER = "mflux.models.common.schedulers.base_scheduler"
CONFIG_MODULE = "mflux.models.common.config.config"


class FakeArray:
    """The little of mlx's array this module uses: indexing, arithmetic, astype.

    Indexing returns an array rather than a scalar, because mlx does: the code
    under test calls `.astype` on the result of a subtraction between two of them.
    """

    def __init__(self, values, dtype="float32"):
        self.values = list(values)
        self.dtype = dtype

    def __getitem__(self, index):
        return FakeArray([self.values[index]], self.dtype)

    def __sub__(self, other):
        return FakeArray([left - right for left, right in zip(self.values, other.values, strict=True)], self.dtype)

    def __mul__(self, other):
        return FakeArray([left * right for left, right in zip(self.values, other.values, strict=True)], self.dtype)

    def __add__(self, other):
        return FakeArray([left + right for left, right in zip(self.values, other.values, strict=True)], self.dtype)

    def astype(self, dtype):
        return FakeArray(self.values, dtype)

    def tolist(self):
        return list(self.values)


class FakeMLX:
    """mlx.core, for arrays this machine may not have."""

    @staticmethod
    def array(values, dtype=None):
        return FakeArray(values)

    @staticmethod
    def zeros(count):
        return FakeArray([0.0] * count)

    @staticmethod
    def concatenate(parts):
        return FakeArray([value for part in parts for value in part.values])

    @staticmethod
    def arange(count, dtype=None):
        return FakeArray([float(index) for index in range(count)])


class FakeBaseScheduler:
    """mflux's BaseScheduler, which the registered class inherits from."""


class Config:
    """The one field of mflux's Config a schedule is built from."""

    def __init__(self, scheduler="linear", num_inference_steps=STEPS, **rest):
        self.scheduler = scheduler
        self.num_inference_steps = num_inference_steps
        self.rest = rest


class Recorder:
    """Stands in for mflux's registry, which is a dictionary assignment."""

    def __init__(self):
        self.calls = []

    def __call__(self, scheduler_object, scheduler_name=None):
        self.calls.append((scheduler_object, scheduler_name))


def stubs(recorder=None):
    return {
        SCHEDULERS: {"register_contrib": recorder or Recorder()},
        BASE_SCHEDULER: {"BaseScheduler": FakeBaseScheduler},
        "mlx.core": {
            "array": FakeMLX.array,
            "zeros": FakeMLX.zeros,
            "concatenate": FakeMLX.concatenate,
            "arange": FakeMLX.arange,
            "float32": "float32",
        },
        CONFIG_MODULE: {"Config": Config},
    }


def registered(recorder=None):
    """The class `register_schedule` hands to mflux, and the recorder that saw it."""
    recorder = recorder or Recorder()
    with heavy_modules(stubs(recorder)):
        register_schedule()
    scheduler_object, scheduler_name = recorder.calls[0]
    return scheduler_object, scheduler_name, recorder


def test_the_table_is_the_checkpoints_own_eight_nodes():
    assert len(SIGMA_NODES) == STEPS == 8
    # Front-loaded with a last node near 0.41, so the final step is a large jump.
    # This shape is what distinguishes the shipped schedule from a linear one.
    assert SIGMA_NODES[0] == 1.0
    assert SIGMA_NODES[-1] == pytest.approx(0.414568)
    assert all(later < earlier for earlier, later in pairwise(SIGMA_NODES))


def test_the_schedule_is_registered_under_its_own_name():
    scheduler_object, scheduler_name, recorder = registered()

    assert scheduler_name == SCHEDULER_NAME == "qwen_turbo_official"
    assert scheduler_object.SIGMA_NODES == SIGMA_NODES
    assert len(recorder.calls) == 1


def test_registering_twice_is_harmless():
    """The composition root builds this backend on every wiring, so this runs more
    than once in a process. mflux's registry is a dictionary assignment."""
    recorder = Recorder()
    with heavy_modules(stubs(recorder)):
        register_schedule()
        register_schedule()

    assert len(recorder.calls) == 2


def test_the_schedule_appends_the_terminal_zero_mflux_expects():
    scheduler_object, _, _ = registered()

    with heavy_modules(stubs()):
        schedule = scheduler_object(Config())

    assert schedule.sigmas.tolist() == [*SIGMA_NODES, 0.0]
    assert schedule.timesteps.tolist() == [float(index) for index in range(STEPS)]


def test_the_last_step_is_the_large_jump_the_table_was_distilled_for():
    """Seven short steps and one long one. A linear table would move 0.125 to 0."""
    scheduler_object, _, _ = registered()

    with heavy_modules(stubs()):
        schedule = scheduler_object(Config())
        moved = schedule.step(FakeArray([1.0]), STEPS - 1, FakeArray([0.0]))

    assert moved.tolist() == [pytest.approx(-SIGMA_NODES[-1])]


def test_a_step_count_the_table_does_not_have_is_refused_by_name():
    scheduler_object, _, _ = registered()

    with heavy_modules(stubs()):
        for steps in (2, 40):
            with pytest.raises(ValueError, match=rf"8 nodes, but num_inference_steps is {steps}"):
                scheduler_object(Config(num_inference_steps=steps))


def test_a_caller_that_names_no_scheduler_gets_the_official_turbo_one():
    with heavy_modules(stubs()), official_turbo_schedule():
        assert Config().scheduler == SCHEDULER_NAME
        assert Config(num_inference_steps=STEPS).scheduler == SCHEDULER_NAME


def test_a_caller_that_names_a_scheduler_keeps_it():
    """The text-to-image half passes its own, and the patch must not overrule it."""
    with heavy_modules(stubs()), official_turbo_schedule():
        assert Config(scheduler="linear").scheduler == "linear"


def test_the_original_class_is_back_after_the_block():
    with heavy_modules(stubs()):
        before = Config.__init__
        with official_turbo_schedule():
            assert Config.__init__ is not before
        assert Config.__init__ is before
        assert Config().scheduler == "linear"


def test_the_original_class_is_back_when_the_body_raises():
    """A run that dies mid-edit must not leave every later Config patched."""
    with heavy_modules(stubs()):
        before = Config.__init__
        with pytest.raises(RuntimeError, match="the engine died"), official_turbo_schedule():
            raise RuntimeError("the engine died")
        assert Config.__init__ is before
