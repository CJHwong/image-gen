"""What the run in flight is doing, as the page polls it.

The page redraws its progress strip from this alone, so every field has to say
what the run is doing before the first step lands.
"""

from dataclasses import FrozenInstanceError

import pytest

from studio.l1_entities.run_progress import RunProgress


def test_a_poll_before_the_run_starts_reports_nothing_is_running():
    # The page polls from the moment the request is sent. A default that claimed
    # a run was in flight would draw a progress strip for an idle server.
    idle = RunProgress()
    assert not idle.running
    assert idle.stage == ""
    assert (idle.step, idle.total) == (0, 0)
    assert idle.label == ""
    assert not idle.stopping


def test_the_stage_names_which_of_the_two_phases_the_run_is_in():
    # "preparing" covers the model load, which outlasts the steps on a cold
    # start. The page words its wait from this, so the two must stay distinct.
    assert RunProgress(running=True, stage="preparing").stage == "preparing"
    assert RunProgress(running=True, stage="running", step=0, total=40).stage == "running"


def test_the_label_places_the_image_in_its_batch():
    # A batch of one carries no label, so the strip leaves that line out rather
    # than reading "1 of 1" next to a single image.
    batch = RunProgress(running=True, step=3, total=40, label="2 of 4")
    assert batch.label == "2 of 4"
    assert RunProgress(running=True).label == ""


def test_stopping_is_separate_from_running():
    # A cancelled run keeps stepping until the engine reaches its next stop
    # check. The page shows the wait from this flag and keeps polling.
    stopping = RunProgress(running=True, stage="running", step=3, total=40, stopping=True)
    assert stopping.running and stopping.stopping


def test_progress_is_frozen_so_a_poll_cannot_edit_the_answer():
    # The page renders one poll per HTTP response. A frozen answer cannot be
    # edited by the presenter while it reads it.
    # The name travels in a variable, because a literal assignment is what ruff
    # and ty both refuse, and this test has to reach the write.
    progress = RunProgress()
    field = "step"
    with pytest.raises(FrozenInstanceError):
        setattr(progress, field, 1)
