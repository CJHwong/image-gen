import pytest

from studio.l1_entities.errors import BackendBusy, Cancelled
from studio.l3_interface_adapters.api.operations import Operations


def active_id(operations):
    operation = operations.active()
    assert operation is not None
    return operation["id"]


def test_one_operation_owns_the_slot_and_retains_its_result():
    operations = Operations()
    first = operations.begin({"kind": "image", "prompt": "pear"})
    with pytest.raises(BackendBusy):
        operations.begin({"kind": "video"})
    operations.finish(first["id"], {"images": []})
    assert operations.active() is None
    assert operations.get(first["id"])["status"] == "succeeded"
    assert operations.result(first["id"]) == {"images": []}


def test_failures_and_cancellation_release_the_slot():
    operations = Operations()
    first = operations.begin({"kind": "video"})
    operations.fail(first["id"], Cancelled("stopped"))
    assert operations.get(first["id"])["status"] == "cancelled"
    second = operations.begin({"kind": "image"})
    operations.fail(second["id"], ValueError("bad"))
    assert operations.get(second["id"])["error"] == "bad"


@pytest.mark.parametrize("status", ["running", "stopping"])
def test_active_batches_expose_the_retained_manifest(status):
    operations = Operations()
    operation = operations.begin({"kind": "voice"})
    operation_id = operation["id"]
    manifest = {"items": [], "batch_total": 2, "completed": 0}
    operations.retain(operation_id, manifest)
    operations.batch_started(operation_id, 1, 2)
    if status == "stopping":
        operations.stopping(operation_id)
    assert operations.result(operation_id) == manifest
    updated = operations.batch_completed(operation_id, {"audio": "wav"}, {"index": 1})
    assert operations.result(operation_id) == updated
    assert updated["completed"] == 1


@pytest.mark.parametrize("result", [None, {"images": []}, "wav"])
@pytest.mark.parametrize("status", ["running", "stopping"])
def test_active_single_results_still_require_completion(result, status):
    operations = Operations()
    operation = operations.begin({"kind": "voice"})
    if result is not None:
        operations.retain(operation["id"], result)
    if status == "stopping":
        operations.stopping(operation["id"])
    with pytest.raises(BackendBusy, match="has not finished"):
        operations.result(operation["id"])


def test_stopping_only_targets_the_active_operation():
    from studio.l3_interface_adapters.api.operations import OperationMissing

    operations = Operations()
    with pytest.raises(OperationMissing):
        operations.get("unknown")
    first = operations.begin({"kind": "image"})
    assert active_id(operations) == first["id"]
    assert operations.stopping(first["id"])["status"] == "stopping"
    with pytest.raises(BackendBusy):
        operations.result(first["id"])
    operations.finish(first["id"], {"cancelled": True})
    assert operations.get(first["id"])["status"] == "cancelled"
    with pytest.raises(BackendBusy):
        operations.stopping(first["id"])
    second = operations.begin({"kind": "image"})
    operations.fail(second["id"], ValueError("bad"))
    with pytest.raises(OperationMissing):
        operations.result(second["id"])
    assert [one["id"] for one in operations.recent()] == [second["id"], first["id"]]


def test_count_time_and_bytes_bound_retention_without_evicting_active_work():
    from studio.l1_entities.video_job import VideoResult
    from studio.l3_interface_adapters.api.operations import OperationMissing

    now = [0]
    operations = Operations(max_count=1, clock=lambda: now[0], max_age=10, max_bytes=1024)
    first = operations.begin({"kind": "image"})
    operations.finish(first["id"], {})
    second = operations.begin({"kind": "image"})
    assert active_id(operations) == second["id"]
    with pytest.raises(OperationMissing):
        operations.get(first["id"])
    now[0] = 20
    assert active_id(operations) == second["id"]
    operations.finish(second["id"], {})
    assert operations.get(second["id"])["status"] == "succeeded"
    now[0] = 31
    with pytest.raises(OperationMissing):
        operations.get(second["id"])
    third = operations.begin({"kind": "video"})
    operations.finish(third["id"], VideoResult(b"x" * 2048, 8, 8, 9, 24, 7))
    assert operations.recent() == []
    fourth = operations.begin({"kind": "video"})
    operations.finish(fourth["id"], VideoResult(None, 8, 8, 9, 24, None, stub=True))
    assert operations.result(fourth["id"]).stub


def test_voice_retention_counts_the_effective_instruction_in_its_byte_limit():
    from studio.l1_entities.voice_job import SpeechResult

    operations = Operations(max_bytes=1024)
    operation = operations.begin({"kind": "voice"})
    operations.finish(operation["id"], SpeechResult(b"wav", 1, 16000, 7, 4, text="word " * 1000))
    assert operations.recent() == []


def test_continuation_expires_only_between_engine_calls():
    now = [0]
    operations = Operations(clock=lambda: now[0])
    first = operations.begin({"kind": "image", "client_id": "tab"})
    operations.append_image(first["id"], {"png_base64": "png"})
    operations.pause(first["id"], 2)
    with pytest.raises(BackendBusy):
        operations.resume(first["id"], 2, "other")
    now[0] = 29
    operations.resume(first["id"], 2, "tab")
    now[0] = 100
    assert active_id(operations) == first["id"]
    operations.pause(first["id"], 3)
    now[0] = 131
    assert operations.active() is None
    assert operations.get(first["id"])["status"] == "cancelled"
    assert len(operations.result(first["id"])["images"]) == 1
    with pytest.raises(BackendBusy):
        operations.resume(first["id"], 3, "tab")


def test_cancel_after_engine_return_does_not_leave_a_continuation_wait():
    operations = Operations()
    operation = operations.begin({"kind": "image", "client_id": ""})
    operations.stopping(operation["id"])
    operations.pause(operation["id"], 2)
    assert operations.active() is None
    assert operations.get(operation["id"])["status"] == "cancelled"


def test_escalation_blocks_new_owners_until_the_release_finishes():
    import threading

    operations = Operations()
    operation = operations.begin({"kind": "image"})
    assert operations.busy() and not operations.cancelling(operation["id"])
    operations.stopping(operation["id"])
    assert operations.cancelling(operation["id"])
    observed = threading.Event()

    def release():
        operations.finish(operation["id"], {})
        assert operations.active() is None and operations.busy()
        with pytest.raises(BackendBusy):
            operations.begin({"kind": "video"})
        worker = threading.Thread(target=lambda: (operations.recent(), observed.set()))
        worker.start()
        worker.join(2)
        assert observed.is_set(), "release must not hold the operation lock"

    operations.escalate(operation["id"], release)
    assert not operations.busy()
    next_operation = operations.begin({"kind": "video"})
    operations.escalate(operation["id"], lambda: pytest.fail("old cancel released a newer owner"))
    assert active_id(operations) == next_operation["id"]


def test_failed_escalation_releases_its_reservation():
    operations = Operations()
    operation = operations.begin({"kind": "image"})
    operations.stopping(operation["id"])

    def release():
        operations.finish(operation["id"], {})
        raise RuntimeError("release failed")

    with pytest.raises(RuntimeError, match="release failed"):
        operations.escalate(operation["id"], release)
    assert not operations.busy()


def test_model_controls_reserve_the_slot_and_release_it_after_errors():
    operations = Operations()

    def control():
        assert operations.busy()
        with pytest.raises(BackendBusy):
            operations.begin({"kind": "image"})
        with pytest.raises(BackendBusy):
            operations.exclusive(lambda: None)
        raise ValueError("control failed")

    with pytest.raises(ValueError, match="control failed"):
        operations.exclusive(control)
    assert not operations.busy()
