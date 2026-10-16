import json
import subprocess
import sys
import time
from pathlib import Path
from typing import cast

import pytest

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.video_job import VideoJob, VideoReference
from studio.l4_frameworks_and_drivers.ltx25_runner import Ltx25Runner, _stop_process

FILES = (
    "diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors",
    "text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
    "vae/ltx-2.5-video-vae-bf16.safetensors",
    "vae/ltx-2.5-audio-vae-bf16.safetensors",
    "model_patches/ltx-2.5-duration-head-bf16.safetensors",
    "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
)
LIVE_MODEL_DIR = Path.home() / "Library/Caches/models/ltx-2.5"
LIVE_PYTHON_PATH = Path.home() / "Workspace/LTX-2/.venv/bin/python"


def weights(root):
    for relative_path in FILES:
        model_file = root / relative_path
        model_file.parent.mkdir(parents=True, exist_ok=True)
        model_file.write_bytes(b"local model placeholder")


def live_runtime_ready():
    return LIVE_PYTHON_PATH.is_file() and all((LIVE_MODEL_DIR / relative_path).is_file() for relative_path in FILES)


def job(references=()):
    return VideoJob("A kite rises above the beach", 960, 544, 145, 24, 42, references)


def test_runner_builds_official_distilled_command_and_returns_the_mp4(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    calls = []

    def fake_process(command, **options):
        calls.append((command, options))
        Path(command[command.index("--output-path") + 1]).write_bytes(b"real mp4 bytes")

    runner = Ltx25Runner("python", model_dir, process_runner=fake_process)
    keyframes = (
        VideoReference("first.png", b"first png bytes", 24, 0.8),
        VideoReference("second.png", b"second png bytes", 72, 0.6),
    )

    result = runner.run(job(keyframes))

    command, options = calls[0]
    assert command[1:3] == ["-m", "ltx_pipelines.distilled"]
    assert command[command.index("--num-frames") + 1] == "145"
    assert command[command.index("--duration-head-path") + 1].endswith(FILES[-2])
    assert command[command.index("--spatial-upsampler-path") + 1].endswith(FILES[-1])
    image_flags = [index for index, argument in enumerate(command) if argument == "--image"]
    assert len(image_flags) == 2
    assert command[image_flags[0] + 2 : image_flags[0] + 4] == ["24", "0.8"]
    assert command[image_flags[1] + 2 : image_flags[1] + 4] == ["72", "0.6"]
    assert options["check"] is True
    assert options["stdout"] == subprocess.DEVNULL
    assert result.mp4 == b"real mp4 bytes"
    assert (result.width, result.height, result.num_frames, result.frame_rate, result.seed) == (960, 544, 145, 24, 42)
    assert not Path(command[image_flags[0] + 1]).exists()
    assert not Path(command[image_flags[1] + 1]).exists()


def test_runner_wraps_the_distilled_sampler_when_progress_is_requested(tmp_path, monkeypatch):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    calls = []

    def fake_execute(self, command, progress=None, cancelled=None):
        calls.append((command, progress, Path(command[1]).read_text()))
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4 with progress")

    monkeypatch.setattr(Ltx25Runner, "_execute", fake_execute)
    reports = []

    def callback(step, total, phase):
        reports.append((step, total, phase))

    result = Ltx25Runner("python", model_dir).run(job(), callback)

    command, received_callback, wrapper = calls[0]
    assert command[1].endswith("ltx25_progress.py")
    assert command[2:4] == ["--transformer-path", str(model_dir / FILES[0])]
    assert "samplers.tqdm = report_steps" in wrapper
    assert 'phase_state["number"] += 1' in wrapper
    assert received_callback is callback
    assert reports == []
    assert result.mp4 == b"mp4 with progress"


def test_runner_reads_live_progress_records_from_the_child_process():
    reports = []
    command = [
        sys.executable,
        "-c",
        "import sys, time; time.sleep(0.3); sys.stderr.write('notice\\nSTUDIO_STEP 1 1 4\\n'); "
        "sys.stderr.flush(); sys.stderr.write('STUDIO_STEP 2 2 3'); sys.stderr.flush()",
    ]

    Ltx25Runner._execute_with_progress(command, lambda step, total, phase: reports.append((step, total, phase)))

    assert reports == [(1, 4, 1), (2, 3, 2)]


def test_runner_drains_child_stderr_without_a_progress_callback():
    command = [sys.executable, "-c", "import sys; sys.stderr.write('ready\\n')"]

    Ltx25Runner._execute_with_progress(command, None)


def test_runner_reports_a_streamed_pipeline_failure():
    command = [sys.executable, "-c", "raise SystemExit(2)"]

    with pytest.raises(StudioError, match="pipeline failed with exit status 2"):
        Ltx25Runner("python", ".")._execute(command, lambda _step, _total, _phase: None)


def test_runner_returns_after_streaming_progress():
    runner = Ltx25Runner("python", ".", process_runner=lambda *_args, **_options: pytest.fail())

    def callback(_step, _total, _phase):
        return None

    runner._execute([sys.executable, "-c", "pass"], callback)


def test_runner_terminates_the_child_when_cancelled():
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    started = time.monotonic()

    with pytest.raises(Cancelled, match="video generation was cancelled"):
        Ltx25Runner._execute_with_progress(
            command,
            None,
            lambda: time.monotonic() - started >= 0.15,
        )

    assert time.monotonic() - started < 5


def test_runner_propagates_cancellation_without_wrapping_it():
    command = [sys.executable, "-c", "import time; time.sleep(30)"]

    with pytest.raises(Cancelled, match="video generation was cancelled"):
        Ltx25Runner("python", ".")._execute(command, cancelled=lambda: True)


def test_runner_checks_cancellation_after_the_child_exits():
    checks = iter((False, True))
    command = [sys.executable, "-c", "pass"]

    with pytest.raises(Cancelled, match="video generation was cancelled"):
        Ltx25Runner._execute_with_progress(command, None, lambda: next(checks))


def test_stop_process_returns_when_the_child_has_already_exited():
    class ExitedProcess:
        def poll(self):
            return 0

        def terminate(self):
            pytest.fail("an exited child must not receive a signal")

    _stop_process(cast(subprocess.Popen, ExitedProcess()))


def test_stop_process_handles_a_child_that_exits_before_terminate():
    class RacedProcess:
        def poll(self):
            return None

        def terminate(self):
            raise ProcessLookupError

        def wait(self, timeout=None):
            pytest.fail("a vanished child must not be waited on")

    _stop_process(cast(subprocess.Popen, RacedProcess()))


def test_stop_process_kills_a_child_that_does_not_stop():
    class StubbornProcess:
        def __init__(self):
            self.wait_count = 0
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            self.wait_count += 1
            if self.wait_count == 1:
                assert timeout == 3
                raise subprocess.TimeoutExpired("ltx", timeout)
            assert self.killed

        def kill(self):
            self.killed = True

    process = StubbornProcess()
    _stop_process(cast(subprocess.Popen, process))

    assert process.wait_count == 2


def test_runner_reports_a_streamed_pipeline_timeout(monkeypatch):
    monkeypatch.setattr("studio.l4_frameworks_and_drivers.ltx25_runner.RUN_TIMEOUT_SECONDS", 0)
    command = [sys.executable, "-c", "import time; time.sleep(5)"]

    with pytest.raises(StudioError, match="timed out after one hour"):
        Ltx25Runner("python", ".")._execute(command, lambda _step, _total, _phase: None)


def test_runner_downloads_missing_weights_once_on_first_generation(tmp_path):
    model_dir = tmp_path / "ltx-models"
    downloads = []
    generations = []

    def fake_download(target_dir):
        downloads.append(target_dir)
        weights(target_dir)

    def fake_process(command, **options):
        generations.append(command)
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4")

    runner = Ltx25Runner(
        "python",
        model_dir,
        process_runner=fake_process,
        model_downloader=fake_download,
    )

    runner.run(job())
    runner.run(job())

    assert downloads == [model_dir]
    assert len(generations) == 2


def test_ltx_weight_download_uses_the_cancellable_child_runner(tmp_path, monkeypatch):
    commands = []

    def fake_execute(command, progress, cancelled):
        commands.append((command, progress, cancelled))
        if command[1] == "-c":
            weights(tmp_path)
            return
        Path(command[command.index("--output-path") + 1]).write_bytes(b"downloaded model video")

    def should_cancel():
        return False

    monkeypatch.setattr(Ltx25Runner, "_execute_with_progress", staticmethod(fake_execute))

    result = Ltx25Runner(sys.executable, tmp_path).run(job(), cancelled=should_cancel)

    command, progress, received_cancel = commands[0]
    assert command[:2] == [sys.executable, "-c"]
    assert "snapshot_download" in command[2]
    assert command[3] == "Lightricks/LTX-2.5"
    assert command[-1] == str(tmp_path)
    assert progress is None
    assert received_cancel is should_cancel
    assert result.mp4 == b"downloaded model video"
    assert commands[1][2] is should_cancel


@pytest.mark.parametrize(
    "failure, error_type, message",
    [
        (FileNotFoundError(), StudioError, "could not start"),
        (subprocess.CalledProcessError(1, "download"), StudioError, "weights download failed"),
        (subprocess.TimeoutExpired("download", 3600), StudioError, "weights download timed out"),
        (Cancelled("stop download"), Cancelled, "stop download"),
    ],
)
def test_ltx_weight_download_reports_failure_and_propagates_cancel(tmp_path, monkeypatch, failure, error_type, message):
    def failed_download(_command, _progress, _cancelled):
        raise failure

    monkeypatch.setattr(Ltx25Runner, "_execute_with_progress", staticmethod(failed_download))

    with pytest.raises(error_type, match=message):
        Ltx25Runner._download_model(sys.executable, tmp_path, None)


def test_default_downloader_requests_official_files_from_hugging_face(tmp_path, monkeypatch):
    model_dir = tmp_path / "ltx-models"
    downloads = []

    def fake_download(command, progress, cancelled):
        downloads.append(
            {
                "repo_id": command[3],
                "allow_patterns": json.loads(command[4]),
                "local_dir": Path(command[5]),
                "progress": progress,
                "cancelled": cancelled,
            }
        )
        weights(Path(command[5]))

    monkeypatch.setattr(Ltx25Runner, "_execute_with_progress", staticmethod(fake_download))

    def fake_process(command, **options):
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4")

    Ltx25Runner("python", model_dir, process_runner=fake_process).run(job())

    assert downloads == [
        {
            "repo_id": "Lightricks/LTX-2.5",
            "allow_patterns": list(FILES),
            "local_dir": model_dir,
            "progress": None,
            "cancelled": None,
        }
    ]


def test_runner_reports_model_download_failure(tmp_path, monkeypatch):
    def fail_download(_command, _progress, _cancelled):
        raise subprocess.CalledProcessError(1, "download")

    monkeypatch.setattr(Ltx25Runner, "_execute_with_progress", staticmethod(fail_download))
    runner = Ltx25Runner("python", tmp_path / "ltx-models")

    with pytest.raises(StudioError, match=r"LTX-2\.5 weights download failed"):
        runner.run(job())


@pytest.mark.parametrize("model_dir", ["", "."])
def test_runner_refuses_to_download_into_the_current_directory(tmp_path, monkeypatch, model_dir):
    downloads = []
    monkeypatch.chdir(tmp_path)
    runner = Ltx25Runner("python", model_dir, model_downloader=lambda target_dir: downloads.append(target_dir))

    with pytest.raises(StudioError, match="dedicated model_dir"):
        runner.run(job())

    assert downloads == []


def test_runner_reports_a_missing_python_environment(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)

    with pytest.raises(StudioError, match="Python executable"):
        Ltx25Runner(str(tmp_path / "missing-python"), model_dir).run(job())


def test_runner_requires_a_configured_python_path(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)

    with pytest.raises(StudioError, match="Set python_path"):
        Ltx25Runner("", model_dir).run(job())


def test_runner_accepts_a_python_executable_path(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)

    def fake_process(command, **options):
        assert command[0] == str(Path(sys.executable).absolute())
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4")

    result = Ltx25Runner(sys.executable, model_dir, process_runner=fake_process).run(job())

    assert result.mp4 == b"mp4"


def test_runner_preserves_a_virtual_environment_python_symlink(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    python_link = tmp_path / "venv" / "bin" / "python"
    python_link.parent.mkdir(parents=True)
    python_link.symlink_to(sys.executable)

    def fake_process(command, **options):
        assert command[0] == str(python_link)
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4")

    result = Ltx25Runner(str(python_link), model_dir, process_runner=fake_process).run(job())

    assert result.mp4 == b"mp4"


def test_runner_reports_incomplete_local_weights(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()

    def no_download(_target_dir):
        return None

    with pytest.raises(StudioError, match="local weights are incomplete"):
        Ltx25Runner("python", model_dir, model_downloader=no_download).run(job())


def test_runner_omits_seed_and_image_flags_when_not_selected(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    command_seen = []

    def fake_process(command, **options):
        command_seen.extend(command)
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4")

    unseeded_job = VideoJob("A kite rises", 960, 544, 145, 24, None)

    Ltx25Runner("python", model_dir, process_runner=fake_process).run(unseeded_job)

    assert "--seed" not in command_seen and "--image" not in command_seen


def test_runner_reports_pipeline_failure_without_printing_stderr(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)

    def fail_process(command, **options):
        raise subprocess.CalledProcessError(2, command, stderr=b"private prompt text")

    with pytest.raises(StudioError, match="pipeline failed") as error:
        Ltx25Runner("python", model_dir, process_runner=fail_process).run(job())

    assert "private prompt text" not in str(error.value)


def test_runner_reports_a_python_start_failure(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)

    def missing_process(command, **options):
        raise FileNotFoundError(command[0])

    with pytest.raises(StudioError, match="could not start"):
        Ltx25Runner("python", model_dir, process_runner=missing_process).run(job())


def test_runner_reports_timeout(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)

    def timeout_process(command, **options):
        raise subprocess.TimeoutExpired(command, options["timeout"])

    with pytest.raises(StudioError, match="timed out"):
        Ltx25Runner("python", model_dir, process_runner=timeout_process).run(job())


def test_runner_requires_the_pipeline_to_write_an_output_file(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)

    with pytest.raises(StudioError, match="did not write an MP4"):
        Ltx25Runner("python", model_dir, process_runner=lambda command, **options: None).run(job())


@pytest.mark.live
@pytest.mark.skipif(not live_runtime_ready(), reason="no local LTX-2.5 runtime and weights")
def test_live_runner_generates_a_short_video_clip():
    result = Ltx25Runner(str(LIVE_PYTHON_PATH), LIVE_MODEL_DIR).run(
        VideoJob("A red paper kite rises above a calm beach", 768, 768, 9, 24, 42)
    )

    assert result.mp4 is not None
    assert len(result.mp4) > 1024
    assert result.mp4[4:8] == b"ftyp"
