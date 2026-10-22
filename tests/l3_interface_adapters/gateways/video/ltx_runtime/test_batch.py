import json
from dataclasses import replace
from typing import Any, cast

import pytest

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.video_job import VideoAudio, VideoJob
from studio.l3_interface_adapters.gateways.video.ltx_runtime.batch import BatchRecords, can_reuse


def job(prompt="a cat", **changes):
    return replace(VideoJob(prompt, 384, 384, 9, 24, 7), **changes)


def test_dynamic_profiles_use_geometry_length_and_measured_memory(monkeypatch):
    from studio.l3_interface_adapters.gateways.video.ltx_runtime import batch

    monkeypatch.setattr(batch, "physical_memory", lambda: 64 * 1024**3)
    model = "dgrauet/ltx-2.5-mlx-q8"
    mid = job(width=768, height=768, num_frames=121)
    high = job(width=1920, height=1088, num_frames=97)
    assert not can_reuse([mid, mid], model)
    assert batch.reuse_policy([mid] * 16, model) is None
    assert batch.reuse_policy([high] * 2, model) == "cleared"
    # The voxel budget permits a longer clip when the spatial size is smaller.
    assert batch.reuse_policy([job(width=1280, height=720, num_frames=121)] * 2, model) == "cleared"
    assert batch.reuse_policy([job(width=1920, height=1088, num_frames=49)] * 2, model) == "offload"
    assert not can_reuse([job(), job()], model)
    assert not can_reuse([], model)
    assert not can_reuse([mid], model)
    assert not can_reuse([mid, mid], "another-model")
    assert not can_reuse([mid, high], model)
    for changes in [
        dict(width=2048, height=1088),
        dict(width=2048, height=256),
        dict(num_frames=129),
        dict(width=1920, height=1088, num_frames=121),
        dict(frame_rate=30),
        dict(audio=VideoAudio(b"a", "a.wav")),
        dict(references=(object(),)),
        dict(edit=object()),
    ]:
        changed = replace(high, **changes)
        assert not can_reuse([changed] * 2, model)
    monkeypatch.setattr(batch, "physical_memory", lambda: 32 * 1024**3)
    assert not can_reuse([high] * 2, model)


def test_physical_memory_failure_disables_reuse(monkeypatch):
    from studio.l3_interface_adapters.gateways.video.ltx_runtime import batch

    monkeypatch.setattr(batch.os, "sysconf", lambda key: 1024)
    assert batch.physical_memory() == 1024**2

    def unavailable(key):
        raise OSError("unknown memory")

    monkeypatch.setattr(batch.os, "sysconf", unavailable)
    assert batch.physical_memory() == 0


def test_records_join_pipe_chunks_and_retain_the_result_before_acknowledgement(tmp_path):
    events = []
    progress = []
    jobs = [job(), job("a dog")]
    commands = [["cli", "--stage1-steps", "8", "--stage2-steps", "3"]] * 2
    records = BatchRecords(
        jobs,
        commands,
        tmp_path,
        lambda index, result: events.append((index, result.mp4)),
        lambda index, total: events.append((index, total)),
        lambda *values: progress.append(values),
        lambda: False,
    )
    records.feed('STUDIO_BATCH:{"event":"start","index":1}\nDenoising: 0%| | 0/8 [x]\r')
    (tmp_path / "1.mp4").write_bytes(b"first")
    records.feed('STUDIO_BATCH:{"event":"done",')
    assert not (tmp_path / "1.ack").exists()
    records.feed('"index":1}\nSTUDIO_BATCH:{"event":"start","index":2}\n')
    assert events == [(1, 2), (1, b"first"), (2, 2)]
    assert (tmp_path / "1.ack").exists()
    assert progress == [(0, 11, 1)]
    assert records.results[0].seed == 7


@pytest.mark.parametrize("contents", [None, b""])
def test_missing_output_fails_without_acknowledgement(tmp_path, contents):
    if contents is not None:
        (tmp_path / "1.mp4").write_bytes(contents)
    records = BatchRecords([job()], [[]], tmp_path, lambda *_: None, lambda *_: None, None, lambda: False)
    records.feed('STUDIO_BATCH:{"event":"start","index":1}\n')
    with pytest.raises(StudioError, match="did not write"):
        records.feed('STUDIO_BATCH:{"event":"done","index":1}\n')
    assert not (tmp_path / "1.ack").exists()


def test_cancellation_before_a_marker_stops_without_acknowledgement(tmp_path):
    records = BatchRecords([job()], [[]], tmp_path, lambda *_: None, lambda *_: None, None, lambda: True)
    with pytest.raises(Cancelled):
        records.feed('STUDIO_BATCH:{"event":"start","index":1}\n')


def test_unrelated_logs_without_progress_are_safe(tmp_path):
    records = BatchRecords([job()], [[]], tmp_path, lambda *_: None, lambda *_: None, None, lambda: False)
    records.feed("loading model\n")
    assert records.results == []


def test_the_child_preencodes_unique_prompts_frees_gemma_and_reuses_one_pipeline(monkeypatch, tmp_path, capsys):
    import sys
    from types import ModuleType, SimpleNamespace

    from studio.l3_interface_adapters.gateways.video.ltx_runtime import mlx_video_batch_child as child

    events = []
    pipelines = []

    class Pipeline:
        def __init__(self, *arguments, **options):
            events.append(("create", arguments, options))
            self.prompt_encoder = SimpleNamespace(
                encode=lambda prompt: (prompt, "audio"), free=lambda: events.append("free")
            )
            pipelines.append(self)

    distilled = cast(Any, ModuleType("ltx_pipelines_mlx.distilled"))
    distilled.DistilledPipeline = Pipeline
    package = cast(Any, ModuleType("ltx_pipelines_mlx"))
    package.distilled = distilled
    mlx = cast(Any, ModuleType("mlx"))
    mx = cast(Any, ModuleType("mlx.core"))
    mx.eval = lambda *values: events.append(("eval", values))
    mlx.core = mx
    cli = cast(Any, ModuleType("ltx_pipelines_mlx.cli"))
    invocations = []

    def main():
        invocations.append(sys.argv[:])
        pipeline = distilled.DistilledPipeline("pack", low_memory=True)
        pipeline._load_text_encoder()
        assert pipeline._encode_text(sys.argv[sys.argv.index("-p") + 1])[1] == "audio"

    cli.main = main
    for name, module in [
        ("mlx", mlx),
        ("mlx.core", mx),
        ("ltx_pipelines_mlx", package),
        ("ltx_pipelines_mlx.distilled", distilled),
        ("ltx_pipelines_mlx.cli", cli),
    ]:
        monkeypatch.setitem(sys.modules, name, module)
    commands = [["cli", "-p", prompt] for prompt in ["cat", "dog", "cat"]]
    manifest = tmp_path / "commands.json"
    manifest.write_text(json.dumps(commands))
    waited = []

    def sleep(seconds):
        waited.append(seconds)
        for index in range(1, 4):
            (tmp_path / f"{index}.ack").touch()

    monkeypatch.setattr(child.time, "sleep", sleep)
    monkeypatch.setattr(sys, "argv", ["child", str(manifest)])
    child.execute(manifest)
    assert len(pipelines) == 1
    assert events == [
        ("create", ("pack",), {"low_memory": False}),
        ("eval", ("cat", "audio")),
        ("eval", ("dog", "audio")),
        "free",
    ]
    assert invocations == commands
    assert waited == [0.05]
    stderr = capsys.readouterr().err
    assert stderr.count('"event": "start"') == 3
    assert stderr.count('"event": "done"') == 3
    assert "Batch prompt encoding:" in stderr

    import runpy

    distilled.DistilledPipeline = Pipeline
    for arguments in ([str(manifest)], ["resident", str(manifest)]):
        distilled.DistilledPipeline = Pipeline
        monkeypatch.setattr(sys, "argv", ["child", *arguments])
        runpy.run_path(child.__file__, run_name="__main__")


@pytest.mark.parametrize(
    "record",
    [
        "STUDIO_BATCH:not-json\n",
        "STUDIO_BATCH:[]\n",
        'STUDIO_BATCH:{"event":"start","index":2}\n',
        'STUDIO_BATCH:{"event":"wat","index":1}\n',
        'STUDIO_BATCH:{"event":"done","index":1}\n',
        'STUDIO_BATCH:{"event":"start","index":true}\n',
    ],
)
def test_invalid_child_events_fail_without_an_acknowledgement(tmp_path, record):
    records = BatchRecords([job()], [[]], tmp_path, lambda *_: None, lambda *_: None, None, lambda: False)
    with pytest.raises(StudioError, match="invalid item event"):
        records.feed(record)
    assert not (tmp_path / "1.ack").exists()


def test_duplicate_start_events_fail(tmp_path):
    records = BatchRecords([job()], [[]], tmp_path, lambda *_: None, lambda *_: None, None, lambda: False)
    records.feed('STUDIO_BATCH:{"event":"start","index":1}\n')
    with pytest.raises(StudioError, match="invalid item event"):
        records.feed('STUDIO_BATCH:{"event":"start","index":1}\n')


@pytest.mark.parametrize("policy,low_memory", [("cleared", False), ("offload", True)])
def test_cleanup_profile_bounds_cache_and_preserves_each_stage_result(monkeypatch, policy, low_memory):
    import sys
    from types import ModuleType

    from studio.l3_interface_adapters.gateways.video.ltx_runtime import mlx_video_batch_child as child

    events = []

    class Pipeline:
        def __init__(self, *args, **options):
            from types import SimpleNamespace

            assert options["low_memory"] is low_memory
            self.prompt_encoder = SimpleNamespace(encode=lambda text: (text,), free=lambda: None)

        def _stage1(self, value):
            return value

        def _upsample_latent(self, value):
            return value

        def _stage2(self, value):
            return value

        def _decode_and_save_video(self, value):
            return value

    distilled = cast(Any, ModuleType("ltx_pipelines_mlx.distilled"))
    distilled.DistilledPipeline = Pipeline
    mx = cast(Any, ModuleType("mlx.core"))
    mx.eval = lambda *args: None
    mx.set_cache_limit = lambda value: events.append(("cache", value))
    memory = cast(Any, ModuleType("ltx_core_mlx.utils.memory"))
    memory.aggressive_cleanup = lambda: events.append("cleanup")
    for name, module in [
        ("ltx_pipelines_mlx.distilled", distilled),
        ("mlx.core", mx),
        ("ltx_core_mlx.utils.memory", memory),
    ]:
        monkeypatch.setitem(sys.modules, name, module)
    child.retain_pipeline([["cli", "-p", "cat"]], policy)
    pipeline = distilled.DistilledPipeline()
    for name in ("_stage1", "_upsample_latent", "_stage2", "_decode_and_save_video"):
        assert getattr(pipeline, name)("unchanged") == "unchanged"
    assert events == [("cache", 1024**3), "cleanup", "cleanup", "cleanup", "cleanup"]


def test_only_the_measured_short_pair_prefers_per_item_execution():
    from studio.l3_interface_adapters.gateways.video.ltx_runtime.batch import prefer_sequential

    model = "dgrauet/ltx-2.5-mlx-q8"
    item = job(width=1920, height=1088, num_frames=17, enhance=True)
    assert prefer_sequential([item, item], model)
    assert not prefer_sequential([item] * 3, model)
    assert not prefer_sequential([item, item], "another-model")
    for changes in [
        dict(num_frames=49),
        dict(width=1280),
        dict(enhance=False),
        dict(edit=object()),
        dict(audio=VideoAudio(b"a", "a.wav")),
        dict(references=(object(),)),
    ]:
        assert not prefer_sequential([replace(item, **changes), item], model)


def test_fast_mode_selects_residency_only_for_the_measured_enhanced_mid_shape(monkeypatch):
    from studio.l3_interface_adapters.gateways.video.ltx_runtime import batch

    monkeypatch.setattr(batch, "physical_memory", lambda: 64 * 1024**3)
    model = "dgrauet/ltx-2.5-mlx-q8"
    first = job(width=768, height=768, num_frames=121, enhance=True, fast_mode=True)
    assert batch.reuse_policy([first] * 2, model) == "resident"
    for changed in [replace(first, fast_mode=False), replace(first, enhance=False), replace(first, width=752)]:
        assert batch.reuse_policy([changed] * 2, model) is None
    assert batch.reuse_policy([first, replace(first, fast_mode=False)], model) is None
    high = replace(first, width=1920, height=1088, num_frames=49)
    assert batch.reuse_policy([high] * 2, model) == "offload"
    monkeypatch.setattr(batch, "physical_memory", lambda: 32 * 1024**3)
    assert batch.reuse_policy([first] * 2, model) is None
