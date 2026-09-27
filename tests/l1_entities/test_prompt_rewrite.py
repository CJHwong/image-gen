"""What a rewriter hands back, and what it hands back when it suggests nothing.

The shape travels as a ratio, not as one of the active backend's size ids,
because the rewriter is a different model that does not know those ids.
"""

from dataclasses import FrozenInstanceError

import pytest

from studio.l1_entities.prompt_rewrite import PromptRewrite


def test_a_rewrite_with_no_shape_leaves_the_size_alone():
    # A rewriter that suggests no shape must not resize the run. None is that
    # answer, and an empty string would have to be tested for separately.
    answer = PromptRewrite(prompt="a longer instruction")
    assert answer.ratio is None
    assert answer.follow_reference is False


def test_the_shape_travels_as_a_ratio():
    # Only the mode knows which sizes it offers, so the rewriter names a shape
    # and the mode maps it onto a size id of its own.
    assert PromptRewrite(prompt="a longer instruction", ratio="3:2").ratio == "3:2"


def test_a_rewrite_can_ask_for_the_shape_of_the_picture_the_run_carries():
    # An edit run must keep its reference's shape even when the rewriter named a
    # ratio of its own. This flag is how it says so.
    answer = PromptRewrite(prompt="a longer instruction", ratio="16:9", follow_reference=True)
    assert answer.follow_reference is True
    assert answer.ratio == "16:9"


def test_a_rewrite_is_frozen_so_the_caller_cannot_edit_the_answer():
    # The use case reads the same answer twice, once for the prompt and once for
    # the shape. A mutable answer could differ between the two reads.
    # The name travels in a variable, because a literal assignment is what ruff
    # and ty both refuse, and this test has to reach the write.
    answer = PromptRewrite(prompt="a longer instruction")
    field = "prompt"
    with pytest.raises(FrozenInstanceError):
        setattr(answer, field, "another instruction")
