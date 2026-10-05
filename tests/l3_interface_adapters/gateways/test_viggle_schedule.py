"""The patch that gives the edit path the viggle schedule, and the day it goes.

mflux 0.21.0's edit variant cannot select a scheduler. Until it can, this module
patches `Config`'s default for the length of one call. The first test here is the
tripwire: it reads the installed mflux, and it fails on the day upstream adds the
argument, which is the signal to delete the module.

Nothing here imports mflux for real. `find_spec` locates the package without
executing it, and the rest stub the two modules the patch touches.
"""

import importlib.util
from pathlib import Path

import pytest

from studio.l3_interface_adapters.gateways.viggle_schedule import viggle_schedule
from tests.support.heavy import heavy_modules

# The edit variant, read straight off disk. Importing it would pull mlx and the
# whole model tree, and the only thing this test needs is its source text.
EDIT_VARIANT = "models/qwen21/variants/edit/qwen_image_21_edit.py"

STUBS = {
    "mflux.models.common.config.config": {},
    "mflux.models.qwen21.model.qwen21_scheduler": {},
}


class FakeConfig:
    """mflux's Config, keeping only the field this patch moves."""

    def __init__(self, scheduler="linear", **rest):
        self.scheduler = scheduler
        self.rest = rest


def edit_variant_source() -> str:
    spec = importlib.util.find_spec("mflux")
    assert spec is not None and spec.origin is not None, "mflux is not installed"
    return (Path(spec.origin).parent / EDIT_VARIANT).read_text(encoding="utf-8")


def edit_generate_image_signature() -> str:
    """The edit variant's parameter list, and only that.

    The body is not read: it calls `config.scheduler.sigmas`, so the word appears
    there without any argument being named after it. Reading the whole method
    would fail on the very thing this patch works around.
    """
    return edit_variant_source().split("def generate_image(", 1)[1].split(") ->", 1)[0]


def test_upstream_still_lacks_a_scheduler_argument():
    """The day this fails, mflux has fixed the edit path and this module goes."""
    signature = edit_generate_image_signature()
    assert "scheduler" not in signature, (
        "mflux's edit generate_image now takes a scheduler. Delete "
        "gateways/viggle_schedule.py and pass the argument instead of patching Config."
    )


def test_the_signature_is_the_one_this_test_means_to_read():
    """A guard on the guard: if the split stops finding the parameter list, the
    tripwire above would pass by reading nothing rather than by reading the right
    method."""
    signature = edit_generate_image_signature()
    assert "num_inference_steps" in signature and "output_resolution" in signature


def config_stubs():
    return {**STUBS, "mflux.models.common.config.config": {"Config": FakeConfig}}


def test_a_caller_that_names_no_scheduler_gets_the_viggle_one():
    with heavy_modules(config_stubs()), viggle_schedule():
        assert FakeConfig().scheduler == "viggle_turbo"
        assert FakeConfig(num_inference_steps=6).scheduler == "viggle_turbo"


def test_a_caller_that_names_a_scheduler_keeps_it():
    """The text-to-image half passes its own, and the patch must not overrule it."""
    with heavy_modules(config_stubs()), viggle_schedule():
        assert FakeConfig(scheduler="linear").scheduler == "linear"


def test_the_original_class_is_back_after_the_block():
    with heavy_modules(config_stubs()):
        before = FakeConfig.__init__
        with viggle_schedule():
            assert FakeConfig.__init__ is not before
        assert FakeConfig.__init__ is before
        assert FakeConfig().scheduler == "linear"


def test_the_original_class_is_back_when_the_body_raises():
    """A run that dies mid-edit must not leave every later Config patched."""
    with heavy_modules(config_stubs()):
        before = FakeConfig.__init__
        with pytest.raises(RuntimeError, match="the engine died"), viggle_schedule():
            raise RuntimeError("the engine died")
        assert FakeConfig.__init__ is before
