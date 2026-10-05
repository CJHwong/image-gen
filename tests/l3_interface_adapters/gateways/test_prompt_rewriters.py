from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l3_interface_adapters.gateways.prompt_rewriters import (
    CatalogPromptRewriter,
    NoPromptRewriter,
    StubPromptRewriter,
)


class Catalog(BackendCatalogGateway):
    """A catalog whose active backend the test can move."""

    def __init__(self, active="first"):
        self.active = active

    def get(self, backend_id):
        raise AssertionError("a rewriter never asks the catalog for an engine")

    def visible_ids(self):
        return ()

    def active_id(self):
        return self.active

    def set_active(self, backend_id):
        self.active = backend_id


class Rewriter(PromptRewriterGateway):
    def __init__(self, modes=("generate",)):
        self._modes = modes
        self.seen = []
        self.releases = 0

    def modes(self):
        return self._modes

    def rewrite(self, prompt, mode, references, on_writing, should_stop):
        self.seen.append((prompt, mode, references, on_writing, should_stop))
        return f"longer {prompt}"

    def release(self):
        self.releases += 1


def quick(rewriter):
    """Set the stub's two clocks to zero on the instance.

    The stub's sleeps are real, so a test that reads the order of its calls would
    otherwise wait 4.2 seconds. The instance attribute shadows the class constant,
    so no other test is slowed or changed.
    """
    rewriter.PREPARING_SECONDS = 0
    rewriter.WRITING_SLICE_SECONDS = 0
    return rewriter


def test_the_absent_rewriter_refuses_instead_of_answering():
    # Its empty mode list hides the page's toggle, so a call here comes from a
    # caller that ignored the list. A silent answer would send the prompt on
    # unimproved and look like it worked.
    rewriter = NoPromptRewriter()
    assert rewriter.modes() == ()
    with pytest.raises(InvalidJob, match="no prompt rewriter"):
        rewriter.rewrite("a cat", "generate", (), lambda: None, lambda: False)
    rewriter.release()


def test_the_rewriter_in_force_follows_the_backend_the_page_is_on():
    # A rewriter belongs to a backend and the page may switch backends, so the
    # one in force has to follow the catalog. A stale one would rewrite the
    # prompt for the model that just went away.
    catalog = Catalog("first")
    first, second = Rewriter(), Rewriter(modes=("generate", "edit"))
    rewriter = CatalogPromptRewriter({"first": first, "second": second}, catalog)
    assert rewriter.modes() == ("generate",)

    rewriter.rewrite("a cat", "generate", (), lambda: None, lambda: False)
    catalog.set_active("second")
    assert rewriter.modes() == ("generate", "edit")

    rewriter.rewrite("a dog", "edit", (), lambda: None, lambda: False)
    assert [seen[:3] for seen in first.seen] == [("a cat", "generate", ())]
    assert [seen[:3] for seen in second.seen] == [("a dog", "edit", ())]


def test_the_rewriter_in_force_receives_both_callables():
    # The page needs both: the phase report draws its stop button, and the stop
    # check is what the button sets. A catalog that swallowed either would leave
    # the button wrong for whichever backend is active.
    on_writing, should_stop = Mock(), Mock()
    first = Rewriter()
    CatalogPromptRewriter({"first": first}, Catalog("first")).rewrite("a cat", "generate", (), on_writing, should_stop)
    assert first.seen[0][3:] == (on_writing, should_stop)


def test_a_backend_with_no_rewriter_takes_the_absent_one():
    rewriter = CatalogPromptRewriter({"first": Rewriter()}, Catalog("second"))
    assert rewriter.modes() == ()
    with pytest.raises(InvalidJob, match="no prompt rewriter"):
        rewriter.rewrite("a cat", "generate", (), lambda: None, lambda: False)


def test_release_frees_every_backends_rewriter():
    # The rewriter is a second model and the caller asking for memory wants all
    # of it. Freeing only the active one leaves the other resident.
    first, second = Rewriter(), Rewriter()
    CatalogPromptRewriter({"first": first, "second": second}, Catalog("first")).release()
    assert first.releases == 1 and second.releases == 1


def test_the_stub_answers_with_a_longer_prompt_for_the_page():
    answer = quick(StubPromptRewriter()).rewrite("a cat", "generate", (), lambda: None, lambda: False)
    assert answer.prompt == "a cat A longer version of it, written for the stub."
    assert answer.ratio == "3:2"  # the page checks that a suggested shape becomes a size


def test_the_stub_reports_its_writing_phase_once():
    # The page offers its stop button only once the model writes, so the stub has
    # to say when it crosses that line, exactly as the real one does.
    on_writing = Mock()
    quick(StubPromptRewriter()).rewrite("a cat", "generate", (), on_writing, lambda: False)
    on_writing.assert_called_once_with()


def test_a_stop_during_the_stub_preparing_phase_writes_nothing():
    # A stop cannot land during the load, on the stub as on the real rewriter. It
    # is remembered instead, and nothing is written after it.
    on_writing = Mock()
    with pytest.raises(Cancelled):
        quick(StubPromptRewriter()).rewrite("a cat", "generate", (), on_writing, lambda: True)
    on_writing.assert_not_called()


def test_a_stop_between_the_stub_slices_raises():
    # The stop is read between segments, so it lands within one segment and never
    # after the whole write has finished.
    on_writing = Mock()
    should_stop = Mock(side_effect=[False, True])
    with pytest.raises(Cancelled):
        quick(StubPromptRewriter()).rewrite("a cat", "generate", (), on_writing, should_stop)
    on_writing.assert_called_once_with()


def test_the_stub_reports_the_modes_the_page_can_offer():
    # It reports every mode the qwen21 rewriter serves, so the page's toggle can
    # be checked on a machine with no GPU.
    rewriter = StubPromptRewriter()
    assert rewriter.modes() == ("generate", "edit")
    rewriter.release()
