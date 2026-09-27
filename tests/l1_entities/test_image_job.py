"""One image to make, and the image that comes back.

Images cross the core as PNG bytes, so every test here builds a job without
decoding anything.
"""

from dataclasses import FrozenInstanceError

import pytest

from studio.l1_entities.image_job import ImageJob, ImageResult, OptionValue, ReferenceImage

PHOTO = ReferenceImage(png=b"ref", width=640, height=480)


def test_a_job_without_a_picture_carries_no_reference():
    # Generate takes no reference. The default is an empty tuple, so a job that
    # appends later builds a new one instead of editing a shared list.
    job = ImageJob(mode="generate", prompt="a cat", seed=7, options={"steps": 4})
    assert job.references == ()


def test_a_job_with_a_picture_carries_it_with_its_size():
    # The adapters resize from these two numbers, and they must travel with the
    # bytes or the edit mode cannot keep the shape of its reference.
    job = ImageJob(mode="edit", prompt="make it blue", seed=7, options={}, references=(PHOTO,))
    assert job.references[0].png == b"ref"
    assert (job.references[0].width, job.references[0].height) == (640, 480)


def test_a_job_is_frozen_so_a_run_cannot_edit_the_one_it_was_handed():
    # The batch loop reuses one request for several images. A mutable job would
    # let a later image change what an earlier one recorded it asked for.
    # The name travels in a variable, not as a literal: a literal assignment is
    # what ruff and ty both refuse, and this test has to reach the write.
    job = ImageJob(mode="generate", prompt="a cat", seed=7, options={})
    field = "prompt"
    with pytest.raises(FrozenInstanceError):
        setattr(job, field, "a dog")


def test_the_option_value_alias_names_what_a_form_field_parses_to():
    # ParamSpec.parse returns exactly these three types. The alias is the promise
    # every gateway reads its options under.
    assert OptionValue == str | int | float


def test_the_result_carries_the_seed_and_the_steps_that_were_run():
    # The page shows both, and the seed is what makes a good image repeatable.
    result = ImageResult(png=b"png", width=8, height=8, seed=7, steps=40)
    assert (result.seed, result.steps) == (7, 40)
    assert result.png == b"png"
