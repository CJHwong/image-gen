import threading
from dataclasses import replace
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import BackendBusy, Cancelled
from studio.l1_entities.voice_job import SpeechJob, SpeechResult
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway
from studio.l2_use_cases.run_voice_use_case import RunVoiceUseCase
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway


def setup():
    backend = Mock(spec=VoiceBackendGateway)
    backend.run.side_effect = lambda job, on_step, should_stop: SpeechResult(b"wav", 2, 16000, job.seed, 4)
    progress = InMemoryProgressGateway()
    lock = threading.Lock()
    residency = Mock(spec=ModelResidencyGateway)
    return RunVoiceUseCase(backend, progress, lock, residency), backend, progress, lock, residency


def job(mode="design", seed=7):
    return SpeechJob(mode, "Read this line.", seed, {"voice": "A calm clear narrator."})


def test_single_voice_run_loads_model_and_clears_progress():
    use_case, backend, progress, lock, residency = setup()
    result = use_case.execute(job())
    assert result.seed == 7
    assert result.text == "Read this line."
    backend.load.assert_called_once()
    residency.activate.assert_called_once_with("auk")
    assert not lock.locked()
    assert not progress.snapshot().running


def test_batch_preserves_requested_modes_and_does_not_insert_output_references():
    use_case, backend, _, lock, _ = setup()
    events = []
    results = use_case.execute_batch(
        [job(), replace(job(seed=8), text="Read a different line."), job("edit", 9)],
        lambda index, result: events.append(("completed", index, result.seed, lock.locked())),
        lambda index, total: events.append(("started", index, total, lock.locked())),
    )
    jobs = [call.args[0] for call in backend.run.call_args_list]
    assert [entry.mode for entry in jobs] == ["design", "design", "edit"]
    assert jobs[1].text == "Read a different line."
    assert all(entry.references == () for entry in jobs)
    assert [result.seed for result in results] == [7, 8, 9]
    assert events == [
        ("started", 1, 3, True),
        ("completed", 1, 7, True),
        ("started", 2, 3, True),
        ("completed", 2, 8, True),
        ("started", 3, 3, True),
        ("completed", 3, 9, True),
    ]
    backend.load.assert_called_once()


def test_busy_engine_never_loads_voice():
    use_case, backend, _, lock, _ = setup()
    lock.acquire()
    with pytest.raises(BackendBusy):
        use_case.execute(job())
    backend.load.assert_not_called()
    lock.release()


def test_each_batch_start_publishes_fresh_progress_before_the_item_index():
    use_case, backend, progress, _, _ = setup()
    snapshots = []

    def generate(entry, on_step, should_stop):
        on_step(4, 4)
        return SpeechResult(b"wav", 2, 16000, entry.seed, 4)

    backend.run.side_effect = generate
    use_case.execute_batch(
        [job(), job(seed=8)],
        lambda index, result: None,
        lambda index, total: snapshots.append((index, progress.snapshot())),
    )
    assert [index for index, _state in snapshots] == [1, 2]
    assert [(state.stage, state.step, state.total, state.kind) for _index, state in snapshots] == [
        ("preparing", 0, 0, "voice"),
        ("preparing", 0, 0, "voice"),
    ]


def test_cancel_between_items_keeps_the_first_callback_result():
    use_case, backend, progress, lock, _ = setup()
    completed = []

    def retain(index, result):
        completed.append(result)
        progress.request_cancel()

    with pytest.raises(Cancelled):
        use_case.execute_batch([job(), job()], retain, lambda index, total: None)
    assert len(completed) == 1
    assert backend.run.call_count == 1
    assert not lock.locked()


@pytest.mark.parametrize("cancel", [False, True])
def test_engine_failure_releases_slot_and_reports_latched_cancellation(cancel):
    use_case, backend, progress, lock, _ = setup()

    def fail():
        if cancel:
            progress.request_cancel()
        raise RuntimeError("failed to load")

    backend.load.side_effect = fail
    with pytest.raises(Cancelled if cancel else RuntimeError):
        use_case.execute(job())
    assert not lock.locked()
    assert not progress.snapshot().running


def test_loading_watcher_checks_until_cancel_then_releases_backend():
    use_case, backend, progress, _, _ = setup()
    finished = Mock(spec=threading.Event)
    finished.wait.side_effect = [False, False]
    cancel = Mock(side_effect=[False, True])
    progress.cancel_requested = cancel
    use_case._watch_loading(finished)
    backend.release.assert_called_once()
    assert finished.wait.call_count == 2


def test_batch_preserves_distinct_voice_descriptions_and_character_conversion():
    use_case, backend, _, _, _ = setup()
    original = job()
    other_voice = replace(original, options={"voice": "A deep older narrator."})
    other_conversion = replace(original, options={"voice": original.options["voice"], "convert": "off"})
    backend.run.side_effect = lambda entry, on_step, should_stop: SpeechResult(
        str(entry.seed).encode(), 2, 16000, entry.seed, 4
    )
    jobs = [
        original,
        replace(other_voice, seed=8),
        replace(other_conversion, seed=9),
        replace(original, seed=10),
        replace(other_voice, seed=11),
        replace(other_conversion, seed=12),
    ]
    use_case.execute_batch(jobs, lambda index, result: None, lambda index, total: None)
    executed = [call.args[0] for call in backend.run.call_args_list]
    assert executed == jobs
    assert backend.prepare_batch.call_args.args[0] == jobs


def test_catalog_voice_run_activates_the_selected_model_and_refuses_stale_choice():
    from studio.l1_entities.errors import BackendChanged
    from studio.l3_interface_adapters.gateways.in_memory_voice_backend_catalog_gateway import (
        InMemoryVoiceBackendCatalogGateway,
    )

    use_case, backend, progress, lock, residency = setup()
    catalog = InMemoryVoiceBackendCatalogGateway({"auk": backend, "auk_base": backend}, "auk_base", ("auk", "auk_base"))
    use_case = RunVoiceUseCase(backend, progress, lock, residency, catalog)
    with pytest.raises(BackendChanged):
        use_case.execute(job(), "auk")
    assert not lock.locked()
    use_case.execute(job(), "auk_base")
    residency.activate.assert_called_once_with("auk_base")
