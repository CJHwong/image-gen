"""What the page draws at start: the active backend, the pickable ones, the rewrite toggle.

The catalog decides what the page may offer, so a registered backend that is not
visible stays off the list. The rewrite modes come from the rewriter in force: an
empty list hides the page's toggle, rather than offering a button that always refuses.
"""

from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.describe_studio_use_case import DescribeStudioUseCase
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from tests.support.fakes import FakeBackendGateway


class Rewriter(PromptRewriterGateway):
    """A rewriter with a fixed mode list, so the view's list is the only thing under test."""

    def __init__(self, modes: tuple[str, ...]):
        self._modes = modes

    def modes(self):
        return self._modes

    def rewrite(self, prompt: str, mode: str, references: tuple[ReferenceImage, ...]) -> PromptRewrite:
        raise AssertionError("describing the studio never rewrites a prompt")

    def release(self):
        pass


def catalog():
    first = FakeBackendGateway("first", "First")
    second = FakeBackendGateway("second", "Second")
    hidden = FakeBackendGateway("hidden", "Hidden")
    return InMemoryBackendCatalogGateway(
        {"first": first, "second": second, "hidden": hidden}, default_id="first", visible_ids=("first", "second")
    )


def test_the_view_carries_the_active_backend_and_the_visible_ones():
    view = DescribeStudioUseCase(catalog(), Rewriter(("generate", "edit"))).execute()
    assert view.active.backend_id == "first" and view.active.name == "First"
    assert view.backends == (("first", "First", ""), ("second", "Second", ""))
    assert view.rewrite_modes == ("generate", "edit")


def test_a_models_description_travels_with_its_name():
    """The picker says what each model is, so the line has to reach the page with
    the name rather than be looked up again there."""
    described = FakeBackendGateway("one", "One", description="Six steps, no guidance.")
    catalog = InMemoryBackendCatalogGateway({"one": described}, default_id="one", visible_ids=("one",))
    assert DescribeStudioUseCase(catalog, Rewriter(())).execute().backends == (
        ("one", "One", "Six steps, no guidance."),
    )


def test_a_backend_the_page_cannot_offer_is_left_off_the_list():
    view = DescribeStudioUseCase(catalog(), Rewriter(("generate",))).execute()
    assert [backend_id for backend_id, _, _ in view.backends] == ["first", "second"]


def test_a_backend_with_no_rewriter_offers_no_rewrite_modes():
    view = DescribeStudioUseCase(catalog(), Rewriter(())).execute()
    assert view.rewrite_modes == ()
