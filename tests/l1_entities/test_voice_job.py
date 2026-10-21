from dataclasses import FrozenInstanceError

import pytest

from studio.l1_entities.voice_job import OptionValue, ReferenceAudio, SpeechJob, SpeechResult


def test_a_job_without_a_clip_carries_no_reference():
    assert SpeechJob(mode="design", text="hello", seed=7, options={}).references == ()


def test_a_job_carries_its_clip_with_length_and_rate():
    clip = ReferenceAudio(wav=b"wav", seconds=2.5, sample_rate=16000)
    job = SpeechJob(mode="clone", text="hello", seed=7, options={}, references=(clip,))
    assert (job.references[0].seconds, job.references[0].sample_rate) == (2.5, 16000)


def test_a_job_is_frozen_so_a_run_cannot_edit_the_one_it_was_handed():
    job = SpeechJob(mode="design", text="hello", seed=7, options={})
    field = "text"
    with pytest.raises(FrozenInstanceError):
        setattr(job, field, "bye")


def test_the_option_value_alias_names_what_a_form_field_parses_to():
    assert OptionValue == str | int | float


def test_the_result_carries_the_seed_and_the_steps_that_were_run():
    result = SpeechResult(wav=b"wav", seconds=1.0, sample_rate=24000, seed=7, steps=4)
    assert (result.seed, result.steps) == (7, 4)
