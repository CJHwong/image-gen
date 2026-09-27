import pytest

from studio.l1_entities.capabilities import Capabilities, Choice, ModeSpec, ParamSpec
from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.image_job import ImageJob, ImageResult, ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.rewrite_prompt_use_case import RewritePromptUseCase, RewriteRequest

SIZE = ParamSpec(
    id="size",
    kind="choice",
    default="1152x768",
    choices=(
        Choice("1024x1024", "1024 x 1024"),
        Choice("1152x768", "1152 x 768 (3:2)"),
        Choice("768x1152", "768 x 1152 (2:3)"),
        Choice("match", "Match reference"),
    ),
)
RESOLUTION = ParamSpec(
    id="resolution",
    kind="choice",
    default="match",
    choices=(Choice("match", "Match the reference"), Choice("512", "about 512 x 512")),
)
STEPS = ParamSpec(id="steps", kind="number", default=20, minimum=1, maximum=50, integer=True)
# The generate form carries its number knobs beside the size list. Only a choice
# names a width and a height, so the shape reader has to skip the rest.
GENERATE = ModeSpec(id="generate", label="Generate", params=(STEPS, SIZE), max_references=1)
EDIT = ModeSpec(id="edit", label="Edit", params=(RESOLUTION,), min_references=1, max_references=10)
CAPS = Capabilities(backend_id="fake", name="Fake", badge="bf16", modes=(GENERATE, EDIT), max_batch=1)


class Catalog(BackendCatalogGateway):
    def __init__(self):
        self._backends = {"fake": Backend()}

    def get(self, backend_id):
        return self._backends[backend_id]

    def visible_ids(self):
        return ("fake",)

    def active_id(self):
        return "fake"

    def set_active(self, backend_id):
        pass


class Backend(ImageBackendGateway):
    def __init__(self):
        self.releases = 0

    def capabilities(self):
        return CAPS

    def load(self):
        pass

    def run(self, job: ImageJob, on_step, should_stop) -> ImageResult:
        raise AssertionError("a rewrite never runs the image engine")

    def release(self):
        self.releases += 1


class Rewriter(PromptRewriterGateway):
    def __init__(self, answer: PromptRewrite, modes=("generate", "edit")):
        self.answer = answer
        self._modes = modes
        self.seen: tuple[str, str, tuple[ReferenceImage, ...]] | None = None

    def modes(self):
        return self._modes

    def rewrite(self, prompt, mode, references):
        self.seen = (prompt, mode, references)
        return self.answer

    def release(self):
        pass


def use_case(catalog, rewriter):
    return RewritePromptUseCase(rewriter, catalog, clock=iter([10.0, 12.5]).__next__)


def test_the_engines_are_freed_before_the_rewriter_runs():
    # The rewriter is a second model and does not fit beside an engine, so the
    # engines go first. Without this the edit pipeline is still resident when
    # 18.84 GB of rewriter asks for room.
    catalog = Catalog()
    RewritePromptUseCase(Rewriter(PromptRewrite(prompt="longer")), catalog).execute(
        RewriteRequest(prompt="a cat", mode="generate")
    )
    assert catalog.get("fake").releases == 1


def test_the_shape_the_rewriter_asked_for_becomes_a_declared_size():
    catalog = Catalog()
    response = use_case(catalog, Rewriter(PromptRewrite(prompt="longer", ratio="3:2"))).execute(
        RewriteRequest(prompt="a cat", mode="generate")
    )
    assert response.size == "1152x768"


def test_a_shape_this_mode_cannot_render_says_nothing():
    # 16:9 is a real shape and this mode has no size for it. Rendering a
    # different shape instead, without saying so, would be the wrong answer.
    catalog = Catalog()
    response = use_case(catalog, Rewriter(PromptRewrite(prompt="longer", ratio="16:9"))).execute(
        RewriteRequest(prompt="a cat", mode="generate")
    )
    assert response.size is None


def test_a_ratio_that_names_no_shape_says_nothing():
    # A malformed ratio has no shape to match. "3:0" carries no height to divide
    # by, and a size invented from it would render a shape nobody asked for.
    catalog = Catalog()
    response = use_case(catalog, Rewriter(PromptRewrite(prompt="longer", ratio="3:0"))).execute(
        RewriteRequest(prompt="a cat", mode="generate")
    )
    assert response.size is None


def test_a_mode_that_declares_no_size_says_nothing():
    # An edit mode sizes itself from the picture it is given, so it declares no
    # width and height at all. A ratio from the rewriter has nothing to match.
    catalog = Catalog()
    response = use_case(catalog, Rewriter(PromptRewrite(prompt="longer", ratio="1:1"))).execute(
        RewriteRequest(prompt="make it night", mode="edit")
    )
    assert response.size is None


def test_a_rewriter_that_follows_the_reference_sets_no_size():
    # An edit sizes itself from the picture it is given, and "match" is already
    # its default, so there is nothing for the rewrite to change.
    catalog = Catalog()
    rewriter = Rewriter(PromptRewrite(prompt="longer", ratio="", follow_reference=True))
    response = use_case(catalog, rewriter).execute(RewriteRequest(prompt="make it night", mode="edit"))
    assert response.size is None
    assert rewriter.seen is not None
    assert rewriter.seen[1] == "edit"


def test_the_elapsed_time_is_reported():
    catalog = Catalog()
    response = use_case(catalog, Rewriter(PromptRewrite(prompt="longer"))).execute(
        RewriteRequest(prompt="a cat", mode="generate")
    )
    assert response.elapsed == 2.5


def test_an_empty_prompt_is_refused_before_anything_loads():
    catalog = Catalog()
    with pytest.raises(InvalidJob, match="Write something to rewrite first"):
        use_case(catalog, Rewriter(PromptRewrite(prompt="longer"))).execute(
            RewriteRequest(prompt="   ", mode="generate")
        )
    assert catalog.get("fake").releases == 0


def test_a_mode_the_rewriter_does_not_serve_is_refused():
    catalog = Catalog()
    rewriter = Rewriter(PromptRewrite(prompt="longer"), modes=("generate",))
    with pytest.raises(InvalidJob, match="rewrites no edit prompt"):
        use_case(catalog, rewriter).execute(RewriteRequest(prompt="a cat", mode="edit"))
