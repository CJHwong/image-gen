"""Bounded results and one reservation shared by every HTTP client."""

import copy
import json
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from studio.l1_entities.errors import BackendBusy, Cancelled, OperationMissing
from studio.l1_entities.video_job import VideoResult
from studio.l1_entities.voice_job import SpeechResult
from studio.l2_use_cases.boundaries.operation_gateway import OperationGateway


class InMemoryOperationGateway(OperationGateway):
    def __init__(
        self,
        max_count: int = 32,
        max_bytes: int = 256 * 1024 * 1024,
        max_age: float = 3600,
        clock: Callable[[], float] = time.time,
    ):
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._results: dict[str, Any] = {}
        self._items: dict[str, list[Any]] = {}
        self._sizes: dict[str, int] = {}
        self._active: str | None = None
        self._reservation: str | None = None
        self._continuations: dict[str, tuple[int, float]] = {}
        self._clock = clock
        self._max_count = max_count
        self._max_bytes = max_bytes
        self._max_age = max_age

    def begin(self, description: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._prune()
            if self._active is not None or self._reservation is not None:
                raise BackendBusy("The studio is busy. Read its state or cancel the active operation.")
            operation_id = uuid.uuid4().hex
            self._records[operation_id] = {
                **description,
                "id": operation_id,
                "status": "running",
                "started_at": self._clock(),
                "finished_at": None,
                "error": None,
                "result_retained": False,
            }
            self._sizes[operation_id] = len(json.dumps(self._records[operation_id]).encode())
            self._active = operation_id
            return self.get(operation_id)

    def busy(self) -> bool:
        with self._lock:
            self._prune()
            return self._active is not None or self._reservation is not None

    def exclusive(self, action: Callable[[], None]) -> None:
        with self._lock:
            if self.busy():
                raise BackendBusy("The studio is busy. Wait for the active operation.")
            self._reservation = "model-control"
        try:
            action()
        finally:
            with self._lock:
                self._reservation = None

    def cancelling(self, operation_id: str) -> bool:
        with self._lock:
            return self._active == operation_id and self._records[operation_id]["status"] == "stopping"

    def escalate(self, operation_id: str, release: Callable[[], None]) -> None:
        with self._lock:
            if not self.cancelling(operation_id):
                return
            self._reservation = operation_id
        try:
            release()
        finally:
            with self._lock:
                self._reservation = None

    def active(self) -> dict[str, Any] | None:
        with self._lock:
            self._prune()
            return self.get(self._active) if self._active else None

    def get(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            self._prune()
            if operation_id not in self._records:
                raise OperationMissing("The operation expired or does not exist.")
            return copy.deepcopy(self._records[operation_id])

    def recent(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune()
            return copy.deepcopy(list(reversed(self._records.values())))

    def result(self, operation_id: str) -> Any:
        with self._lock:
            record = self.get(operation_id)
            result = self._results.get(operation_id)
            batch_manifest = isinstance(result, dict) and "items" in result
            if record["status"] in ("running", "stopping") and not batch_manifest:
                raise BackendBusy("The operation has not finished.")
            if operation_id not in self._results:
                raise OperationMissing("This operation has no retained result.")
            return self._results[operation_id]

    def stopping(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            self.get(operation_id)
            if self._active != operation_id:
                raise BackendBusy("This operation is no longer active.")
            self._records[operation_id]["status"] = "stopping"
            if operation_id in self._continuations:
                self._end_continuation(operation_id)
            return self.get(operation_id)

    def retain(self, operation_id: str, result: object) -> None:
        with self._lock:
            self._results[operation_id] = result
            record = self._records[operation_id]
            record["result_retained"] = True
            result_size = result_bytes(result) + sum(result_bytes(item) for item in self._items.get(operation_id, []))
            self._sizes[operation_id] = len(json.dumps(record).encode()) + result_size

    def append_image(self, operation_id: str, image: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            previous = self._results.get(operation_id, {"images": []})
            result = {"images": [*previous["images"], image]}
            self.retain(operation_id, result)
            return result

    def batch_started(self, operation_id, index, total):
        with self._lock:
            self._records[operation_id].update(batch_index=index, batch_total=total)

    def batch_completed(self, operation_id, result, metadata):
        with self._lock:
            self._items.setdefault(operation_id, []).append(result)
            self._records[operation_id]["batch_completed"] = len(self._items[operation_id])
            previous = self._results.get(
                operation_id, {"items": [], "batch_total": self._records[operation_id]["batch_total"]}
            )
            manifest = {
                **previous,
                "items": [*previous["items"], metadata],
                "completed": len(self._items[operation_id]),
            }
            self.retain(operation_id, manifest)
            return manifest

    def item_result(self, operation_id, index):
        with self._lock:
            self.get(operation_id)
            items = self._items.get(operation_id, [])
            if not 1 <= index <= len(items):
                raise OperationMissing("This batch item has no retained result.")
            return items[index - 1]

    def pause(self, operation_id: str, next_index: int) -> None:
        with self._lock:
            self._continuations[operation_id] = (next_index, self._clock() + 30)
            if self._records[operation_id]["status"] == "stopping":
                self._end_continuation(operation_id)

    def resume(self, operation_id: str, index: int, client_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.get(operation_id)
            expected = self._continuations.get(operation_id)
            if (
                self._active != operation_id
                or expected is None
                or expected[0] != index
                or record["client_id"] != client_id
            ):
                raise BackendBusy("This batch continuation is no longer active.")
            del self._continuations[operation_id]
            return record

    def _end_continuation(self, operation_id: str) -> None:
        self._records[operation_id].update(status="cancelled", finished_at=self._clock())
        del self._continuations[operation_id]
        self._active = None

    def finish(self, operation_id: str, result: object) -> float:
        with self._lock:
            record = self._records[operation_id]
            cancelled = isinstance(result, dict) and result.get("cancelled") is True
            record.update(status="cancelled" if cancelled else "succeeded", finished_at=self._clock())
            if isinstance(result, VideoResult):
                record.update(
                    width=result.width,
                    height=result.height,
                    num_frames=result.num_frames,
                    frame_rate=result.frame_rate,
                    seed=result.seed,
                )
            if isinstance(result, SpeechResult):
                record.update(
                    seconds=result.seconds,
                    sample_rate=result.sample_rate,
                    seed=result.seed,
                    steps=result.steps,
                    prompt=result.text or record.get("prompt", ""),
                )
            self.retain(operation_id, result)
            self._active = None
            self._prune()
            return record["finished_at"]

    def fail(self, operation_id: str, error: Exception) -> None:
        with self._lock:
            self._records[operation_id].update(
                status="cancelled" if isinstance(error, Cancelled) else "failed",
                finished_at=self._clock(),
                error=str(error),
            )
            self._active = None
            self._prune()

    def _prune(self) -> None:
        if self._active in self._continuations and self._clock() >= self._continuations[self._active][1]:
            self._end_continuation(self._active)
        for operation_id in list(self._records):
            if operation_id == self._active:
                continue
            record = self._records[operation_id]
            expired = self._clock() - record["finished_at"] > self._max_age
            if expired or len(self._records) > self._max_count or sum(self._sizes.values()) > self._max_bytes:
                del self._records[operation_id]
                self._results.pop(operation_id, None)
                self._items.pop(operation_id, None)
                self._sizes.pop(operation_id, None)


def result_bytes(result):
    if isinstance(result, VideoResult):
        return len(result.mp4 or b"")
    if isinstance(result, SpeechResult):
        return len(result.wav)
    return len(json.dumps(result).encode())
