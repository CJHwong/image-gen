from dataclasses import replace

import pytest

from studio.l1_entities.errors import (
    BackendChanged,
    Cancelled,
    InvalidJob,
    MissingPrompt,
    ReferenceExpired,
    UnsupportedMode,
)
from studio.l1_entities.image_job import ReferenceImage
from studio.l2_use_cases.run_image_use_case import RunImageRequest, RunImageUseCase
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway
from studio.l3_interface_adapters.gateways.in_memory_reference_store_gateway import InMemoryReferenceStoreGateway
from tests.unit.fakes import FakeBackendGateway

PHOTO = ReferenceImage(png=b"ref", width=4, height=3)


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
    use_case = RunImageUseCase(catalog, progress, store, seed_source=lambda: 7, clock=lambda: next(clock))
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
