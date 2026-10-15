import threading
from dataclasses import replace

import pytest

from studio.l1_entities.errors import (
    BackendBusy,
    BackendChanged,
    Cancelled,
    InvalidJob,
    MissingPrompt,
    ReferenceExpired,
    UnsupportedMode,
)
from studio.l1_entities.image_job import ReferenceImage
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.run_image_use_case import RunImageRequest, RunImageUseCase
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from studio.l3_interface_adapters.gateways.in_memory_model_residency_gateway import (
    InMemoryModelResidencyGateway,
)
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway
from studio.l3_interface_adapters.gateways.in_memory_reference_store_gateway import InMemoryReferenceStoreGateway
from tests.support.fakes import FakeBackendGateway, FakeModelResidencyGateway, FakeVideoBackendGateway

PHOTO = ReferenceImage(png=b"ref", width=4, height=3)
SECOND = ReferenceImage(png=b"ref2", width=4, height=3)


BASE = RunImageRequest(
    mode="generate", prompt=" a red apple ", seed="42", options={"steps": "2"}, references=(), reference_token=""
)


def request(**overrides):
    return replace(BASE, **overrides)


@pytest.fixture
def studio():
    backend = FakeBackendGateway()
    progress = InMemoryProgressGateway()
    store = InMemoryReferenceStoreGateway()
    catalog = InMemoryBackendCatalogGateway({"fake": backend}, default_id="fake", visible_ids=("fake",))
    clock = iter(range(100, 200, 5))
    use_case = RunImageUseCase(
        catalog,
        progress,
        store,
        seed_source=lambda: 7,
        clock=lambda: next(clock),
        residency=FakeModelResidencyGateway(),
    )
    return use_case, backend, progress, store


def test_one_image(studio):
    use_case, backend, progress, _ = studio
    response = use_case.execute(request())
    assert response.image.seed == 42 and response.image.steps == 2
    assert response.position == "1 image" and response.next_run is None
    assert response.prompt == "a red apple" and response.elapsed == 5
    job = backend.jobs[0]
    assert job.prompt == "a red apple" and job.options == {"steps": 2, "guidance": 1.0}
    assert progress.snapshot().running is False


def test_an_image_run_releases_an_inactive_video_model():
    image = FakeBackendGateway()
    video = FakeVideoBackendGateway()
    residency = InMemoryModelResidencyGateway({"fake": image, "video-fake": video})
    residency.activate("video-fake")
    catalog = InMemoryBackendCatalogGateway({"fake": image}, "fake", ("fake",))
    run = RunImageUseCase(
        catalog,
        InMemoryProgressGateway(),
        InMemoryReferenceStoreGateway(),
        residency=residency,
    )

    run.execute(request())

    assert video.releases == 1
    assert residency.active_id() == "fake"


def test_a_blank_seed_is_drawn(studio):
    use_case, backend, _, _ = studio
    use_case.execute(request(seed=""))
    assert backend.jobs[0].seed == 7


def test_a_bad_seed_is_refused(studio):
    use_case, _, _, _ = studio
    with pytest.raises(InvalidJob, match="seed must be a whole number"):
        use_case.execute(request(seed="4.2"))


def test_a_batch_walks_the_seed(studio):
    use_case, _, _, _ = studio
    response = use_case.execute(request(total=3, options={"steps": "2", "guidance": "2", "cfg": "9"}))
    nxt = response.next_run
    assert response.position == "1 of 3"
    assert (nxt.seed, nxt.index, nxt.total, nxt.reference_token) == (43, 2, 3, "")
    assert nxt.options == {"steps": "2", "guidance": "2"} and nxt.prompt == "a red apple"


def test_references_live_for_the_batch(studio):
    use_case, backend, _, store = studio
    first = use_case.execute(request(references=(PHOTO,), total=2))
    token = first.next_run.reference_token
    assert store.get(token) == (PHOTO,)
    last = use_case.execute(request(reference_token=token, total=2, index=2))
    assert backend.jobs[1].references == (PHOTO,)
    assert last.next_run is None and store.get(token) is None


def test_an_expired_reference_is_named(studio):
    use_case, _, _, _ = studio
    with pytest.raises(ReferenceExpired):
        use_case.execute(request(reference_token="gone", total=2, index=2))


def test_the_mode_bounds_the_references(studio):
    use_case, _, _, _ = studio
    with pytest.raises(InvalidJob, match="Edit needs at least 1 reference image"):
        use_case.execute(request(mode="edit"))


def test_an_unknown_mode_is_refused(studio):
    use_case, _, _, _ = studio
    with pytest.raises(UnsupportedMode):
        use_case.execute(request(mode="control"))


def test_the_batch_size_is_capped(studio):
    use_case, _, _, _ = studio
    with pytest.raises(InvalidJob, match="count must be between 1 and 4"):
        use_case.execute(request(total=5))


def test_a_missing_prompt_uses_the_mode_wording(studio):
    use_case, _, _, _ = studio
    with pytest.raises(MissingPrompt, match=r"An edit instruction is required\."):
        use_case.execute(request(mode="edit", prompt="  ", references=(PHOTO,)))


def test_a_cancel_between_images_stops_the_batch(studio):
    use_case, backend, progress, store = studio
    first = use_case.execute(request(references=(PHOTO,), total=2))
    progress.request_cancel()
    with pytest.raises(Cancelled, match="stopped before this image started"):
        use_case.execute(request(reference_token=first.next_run.reference_token, total=2, index=2))
    assert len(backend.jobs) == 1
    assert store.get(first.next_run.reference_token) is None
    assert progress.cancel_requested() is False


def test_a_fresh_batch_clears_a_stale_cancel(studio):
    use_case, backend, progress, _ = studio
    progress.request_cancel()
    use_case.execute(request())
    assert len(backend.jobs) == 1


def test_a_cancel_mid_run_stops_at_the_step(studio):
    use_case, backend, progress, store = studio
    backend.stop_check = lambda step: step == 2 and progress.request_cancel()
    with pytest.raises(Cancelled, match="stopped at step 2"):
        use_case.execute(request(references=(PHOTO,), total=2))
    assert store.images == {}
    assert progress.snapshot().running is False and progress.cancel_requested() is False


def test_a_failed_run_ends_the_batch(studio):
    use_case, backend, _, store = studio
    backend.fail_with = RuntimeError("out of memory")
    with pytest.raises(RuntimeError, match="out of memory"):
        use_case.execute(request(references=(PHOTO,), total=2))
    assert store.images == {}


def test_progress_shows_the_run(studio):
    use_case, backend, progress, _ = studio
    seen = []
    backend.stop_check = lambda step: seen.append(progress.snapshot())
    use_case.execute(request(total=3, index=2, options={"steps": "2"}))
    assert seen[0].running and seen[0].label == "2 of 3" and seen[0].stage == "preparing"
    assert (seen[1].stage, seen[1].step, seen[1].total) == ("running", 1, 2)


def test_a_cancel_after_the_last_step_still_stops_the_next_image(studio):
    use_case, backend, progress, _ = studio
    engine_run = backend.run

    def run_then_cancel(*args):
        result = engine_run(*args)
        progress.request_cancel()  # lands after the engine's last look at the flag
        return result

    backend.run = run_then_cancel
    first = use_case.execute(request(total=2))
    backend.run = engine_run
    with pytest.raises(Cancelled, match="stopped before this image started"):
        use_case.execute(request(**_chained(first)))
    assert len(backend.jobs) == 1


def test_a_chained_request_checks_the_references(studio):
    use_case, _, _, store = studio
    token = store.add((PHOTO, PHOTO))
    with pytest.raises(InvalidJob):
        use_case.execute(request(reference_token=token, total=2, index=2))


def test_a_batch_stops_when_the_model_changed(studio):
    use_case, backend, _, _ = studio
    with pytest.raises(BackendChanged):
        use_case.execute(request(backend="other"))
    assert backend.jobs == []


def test_the_next_request_names_the_backend(studio):
    use_case, _, _, _ = studio
    assert use_case.execute(request(total=2)).next_run.backend == "fake"


def _chained(response):
    step = response.next_run
    return {
        "seed": str(step.seed),
        "total": step.total,
        "index": step.index,
        "reference_token": step.reference_token,
        "backend": step.backend,
    }


def test_a_second_run_is_refused_while_one_is_in_flight():
    """Another tab's run fails at once. Queued, it would show the first run's
    progress, and its Cancel would stop the first run."""
    backend = FakeBackendGateway()
    progress = InMemoryProgressGateway()
    catalog = InMemoryBackendCatalogGateway({"fake": backend}, default_id="fake", visible_ids=("fake",))
    engine_lock = threading.Lock()
    use_case = RunImageUseCase(
        catalog,
        progress,
        InMemoryReferenceStoreGateway(),
        engine_lock=engine_lock,
        residency=FakeModelResidencyGateway(),
    )
    progress.request_cancel()  # the first run's own cancel, which the refused run must not clear
    with engine_lock, pytest.raises(BackendBusy, match="another tab"):
        use_case.execute(request())
    assert backend.jobs == []
    assert progress.cancel_requested()


class RecordingRewriter(PromptRewriterGateway):
    """A rewriter that writes its release into the test's log, so the order with
    the engine is visible in one place."""

    def __init__(self, log: list[str]):
        self._log = log

    def modes(self):
        return ("generate",)

    def rewrite(self, prompt, mode, references, on_writing, should_stop):
        raise AssertionError("a run never rewrites")

    def release(self):
        self._log.append("rewriter release")


def test_the_rewriter_is_freed_before_the_engine_runs():
    # The rewriter is a second model and does not fit beside an image engine on a
    # 64 GB machine, so the run frees it before the engine takes the GPU. The
    # engine's own release is 3.8s for mflux, which the next load pays back.
    log: list[str] = []
    backend = FakeBackendGateway()
    backend.stop_check = lambda step: log.append(f"engine step {step}")
    catalog = InMemoryBackendCatalogGateway({"fake": backend}, default_id="fake", visible_ids=("fake",))
    use_case = RunImageUseCase(
        catalog,
        InMemoryProgressGateway(),
        InMemoryReferenceStoreGateway(),
        rewriter=RecordingRewriter(log),
        residency=FakeModelResidencyGateway(),
    )
    use_case.execute(request(options={"steps": "1"}))
    assert log == ["rewriter release", "engine step 1"]


def next_of(use_case, previous, **overrides):
    """The next request of a batch, built the way the page builds it from the chain."""
    nxt = previous.next_run
    return use_case.execute(
        request(
            mode=nxt.mode,
            prompt=nxt.prompt,
            seed=str(nxt.seed),
            options=nxt.options,
            references=(),
            reference_token=nxt.reference_token,
            total=nxt.total,
            index=nxt.index,
            each_reference=nxt.each_reference,
            **overrides,
        )
    )


def test_several_references_make_one_picture_by_default(studio):
    """Two images and no flag is the composed edit: one run, both images, one result, and no
    single reference for the page to line that result up with."""
    use_case, backend, _, _ = studio
    response = use_case.execute(request(mode="edit", prompt="a pear", references=(PHOTO, SECOND)))
    assert [job.references for job in backend.jobs] == [(PHOTO, SECOND)]
    assert response.reference == -1


def test_a_batch_may_edit_one_reference_at_a_time(studio):
    """The other meaning of several images: the chain walks them in turn, so the same prompt
    gives every image its own result and each run holds exactly one of them."""
    use_case, backend, _, _ = studio
    first = use_case.execute(
        request(mode="edit", prompt="make it night", references=(PHOTO, SECOND), total=4, each_reference=True)
    )
    assert [job.references for job in backend.jobs] == [(PHOTO,)]
    second = next_of(use_case, first)
    third = next_of(use_case, second)
    fourth = next_of(use_case, third)
    assert [job.references for job in backend.jobs] == [(PHOTO,), (SECOND,), (PHOTO,), (SECOND,)]
    assert [first.reference, second.reference, third.reference, fourth.reference] == [0, 1, 0, 1]
    assert [first.position, fourth.position] == ["1 of 4", "4 of 4"] and fourth.next_run is None


def test_the_count_is_per_reference_when_each_image_is_edited(studio):
    """A reference keeps its place however many images it was asked for, so the mode's own
    bound multiplies with the references: four images each over two is eight, and nine is not.
    Composed, the bound stays what it was, which is four."""
    use_case, backend, _, _ = studio
    use_case.execute(request(mode="edit", prompt="x", references=(PHOTO, SECOND), total=8, each_reference=True))
    assert len(backend.jobs) == 1
    with pytest.raises(InvalidJob, match="count must be between 1 and 8"):
        use_case.execute(request(mode="edit", prompt="x", references=(PHOTO, SECOND), total=9, each_reference=True))
    with pytest.raises(InvalidJob, match="count must be between 1 and 4"):
        use_case.execute(request(mode="edit", prompt="x", references=(PHOTO, SECOND), total=5))


def test_the_mode_decides_whether_each_reference_is_its_own_image():
    """The page asks and the mode declares. Where the declaration is absent, every reference
    goes to one run, which is the behaviour the mode was built for."""
    declared = RunImageUseCase._one_reference(request(mode="edit", each_reference=True), (PHOTO, SECOND), True)
    composed = RunImageUseCase._one_reference(request(mode="edit", each_reference=True), (PHOTO, SECOND), False)
    assert declared == ((PHOTO,), 0)
    assert composed == ((PHOTO, SECOND), -1)


def test_a_mask_is_not_a_member_of_the_batch(studio):
    """The page appends the region mask last, and a mask is one more image of the run that
    carries it. Walking it as a reference would drop it from the first run and edit the mask
    itself in the second, so a request that says one rides keeps the single-image meaning."""
    use_case, backend, _, _ = studio
    mask = ReferenceImage(png=b"mask", width=4, height=3)
    response = use_case.execute(
        request(
            mode="edit",
            prompt="a stone wall in the area marked in <image2>",
            references=(PHOTO, mask),
            total=2,
            each_reference=True,
            mask=True,
        )
    )
    assert [job.references for job in backend.jobs] == [(PHOTO, mask)]
    assert response.reference == -1


def test_the_marker_for_a_mask_travels_the_chain(studio):
    """The second request of a masked batch re-posts what it needs, and which of the images is
    the mask is one of those things. Without it the chain would walk the mask after all."""
    use_case, _, _, _ = studio
    mask = ReferenceImage(png=b"mask", width=4, height=3)
    first = use_case.execute(
        request(mode="edit", prompt="x", references=(PHOTO, mask), total=2, each_reference=True, mask=True)
    )
    assert first.next_run.mask is True and first.next_run.each_reference is True
