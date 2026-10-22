"""Retain completed clips before the child starts its next item."""

import json
import os
import re
import time
from pathlib import Path

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l4_frameworks_and_drivers.mlx_video_runner import _RenderProgress

PREFIX = "STUDIO_BATCH:"


def physical_memory() -> int:
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError):
        return 0


def reuse_policy(jobs: list[VideoJob], model: str) -> str | None:
    """Select within the M5 Pro 64 GiB spike's spatial and temporal memory budget.

    One clip is sampled at a time: item count does not multiply activation memory.
    1920x1088x97 is the largest measured voxel budget; 121 the longest temporal grid.
    The report records matched timings and decoded-frame hashes for each profile.
    """
    if len(jobs) < 2 or model != "dgrauet/ltx-2.5-mlx-q8":
        return None
    if len({(job.width, job.height, job.num_frames, job.frame_rate) for job in jobs}) != 1:
        return None
    if any(job.frame_rate != 24 or job.edit is not None or job.audio is not None or job.references for job in jobs):
        return None
    job = jobs[0]
    pixels = job.width * job.height
    # Measured M5 Pro 64 GiB profile. Fast mode changes compute precision; only
    # this exact enhanced text-only shape established an additional residency win.
    if (
        all(item.fast_mode and item.enhance for item in jobs)
        and (job.width, job.height, job.num_frames) == (768, 768, 121)
        and physical_memory() >= 64 * 1024**3
    ):
        return "resident"
    if (
        pixels <= 768 * 768
        or pixels > 1920 * 1088
        or max(job.width, job.height) > 1920
        or job.num_frames > 121
        or pixels * job.num_frames > 1920 * 1088 * 97
        or physical_memory() < 64 * 1024**3
    ):
        return None
    # Low/mid residency did not beat fresh sequential controls.
    # Short high-resolution clips gain from transformer offload during decode.
    return "cleared" if job.num_frames > 49 else "offload"


def can_reuse(jobs: list[VideoJob], model: str) -> bool:
    return reuse_policy(jobs, model) is not None


def prefer_sequential(jobs: list[VideoJob], model: str) -> bool:
    """Keep the measured short two-clip regression out of automatic selection.

    M5 Pro 64 GiB, LTX-2.5 q8, native enhancement enabled, 2026-10-22:
    two 1920x1088x17 / 24 fps clips: per-item 248.35 s, shared enhancement
    282.15 s, enhancement plus offload reuse 267.10 s. Do not extrapolate
    these timings to another duration, item count, or conditioning mode.
    """
    return (
        len(jobs) == 2
        and model == "dgrauet/ltx-2.5-mlx-q8"
        and all(
            (job.width, job.height, job.num_frames, job.frame_rate) == (1920, 1088, 17, 24)
            and job.enhance
            and job.edit is None
            and job.audio is None
            and not job.references
            for job in jobs
        )
    )


class BatchRecords:
    def __init__(self, jobs, commands, root, completed, started, progress, cancelled):
        self.results: list[VideoResult] = []
        self._jobs = jobs
        self._commands = commands
        self._root: Path = root
        self._completed = completed
        self._started = started
        self._progress = progress
        self._cancelled = cancelled
        self._pending = ""
        self._reporter: _RenderProgress | None = None
        self._active = False
        self.item_started_at: float | None = None

    def feed(self, chunk: str) -> None:
        records = re.split(r"[\r\n]", self._pending + chunk)
        self._pending = records.pop()[-8192:]
        for record in records:
            self._record(record)

    def _record(self, record: str) -> None:
        if not record.startswith(PREFIX):
            if self._reporter:
                self._reporter.feed(record + "\n")
            return
        if self._cancelled():
            raise Cancelled("The video batch was cancelled.")
        try:
            event = json.loads(record[len(PREFIX) :])
        except ValueError:
            raise StudioError("The MLX video batch sent an invalid item event.") from None
        self._check_event(event)
        index = event["index"]
        if event["event"] == "start":
            self.item_started_at = time.monotonic()
            self._active = True
            self._started(index, len(self._jobs))
            self._reporter = _RenderProgress(self._commands[index - 1], self._progress) if self._progress else None
            return
        self._retain(index)
        self._active = False

    def _check_event(self, event) -> None:
        if not isinstance(event, dict):
            raise StudioError("The MLX video batch sent an invalid item event.")
        index = event.get("index")
        expected = "done" if self._active else "start"
        if (
            type(index) is not int
            or index != len(self.results) + 1
            or index > len(self._jobs)
            or event.get("event") != expected
        ):
            raise StudioError("The MLX video batch sent an invalid item event.")

    def _retain(self, index: int) -> None:
        output = self._root / f"{index}.mp4"
        if not output.is_file() or output.stat().st_size == 0:
            raise StudioError("The MLX video pipeline did not write an MP4 file.")
        job = self._jobs[index - 1]
        result = VideoResult(output.read_bytes(), job.width, job.height, job.num_frames, job.frame_rate, job.seed)
        self._completed(index, result)
        self.results.append(result)
        (self._root / f"{index}.ack").touch()
