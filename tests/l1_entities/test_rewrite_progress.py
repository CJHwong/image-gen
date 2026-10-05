"""What the rewrite in flight is doing, as the page polls it.

The page redraws its rewrite strip from this alone, so every field has to say
what the rewriter is doing before the first segment lands.
"""

from dataclasses import FrozenInstanceError

import pytest

from studio.l1_entities.rewrite_progress import RewriteProgress


def test_a_poll_before_the_rewrite_starts_reports_nothing_is_running():
    # The page polls from the moment the request is sent. A default that claimed
    # a rewrite was in flight would draw a busy strip for an idle server.
    idle = RewriteProgress()
    assert not idle.running
    assert idle.stage == "idle"
    assert not idle.stopping


def test_the_stage_names_which_of_the_two_phases_the_rewrite_is_in():
    # "preparing" covers the model load, which outlasts the segments on a cold
    # start. The page words its wait from this, so the two must stay distinct.
    assert RewriteProgress(running=True, stage="preparing").stage == "preparing"
    assert RewriteProgress(running=True, stage="writing").stage == "writing"


def test_stopping_is_separate_from_running():
    # A cancelled rewrite keeps writing until the model reaches its next stop
    # check. The page shows the wait from this flag and keeps polling.
    stopping = RewriteProgress(running=True, stage="writing", stopping=True)
    assert stopping.running and stopping.stopping


def test_rewrite_progress_is_frozen_so_a_poll_cannot_edit_the_answer():
    # The page renders one poll per HTTP response. A frozen answer cannot be
    # edited by the presenter while it reads it.
    # The name travels in a variable, because a literal assignment is what ruff
    # and ty both refuse, and this test has to reach the write.
    progress = RewriteProgress()
    field = "stage"
    with pytest.raises(FrozenInstanceError):
        setattr(progress, field, "writing")
