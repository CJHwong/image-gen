import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.video_job import VideoAudio, VideoJob, VideoReference
from studio.l4_frameworks_and_drivers import mlx_video_runner
from studio.l4_frameworks_and_drivers.mlx_video_runner import MlxVideoRunner, _stop_process


def cli(tmp_path: Path) -> str:
    path = tmp_path / "ltx-2-mlx"
    path.write_text("")
    return str(path)


def capture_execute(monkeypatch, commands):
    def fake_execute(self, command, progress=None, cancelled=None):
        commands.append(command)
        Path(command[command.index("-o") + 1]).write_bytes(b"mp4 bytes")

    monkeypatch.setattr(MlxVideoRunner, "_execute", fake_execute)


def test_a_generate_job_builds_the_distilled_command_with_its_keyframes(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    runner = MlxVideoRunner({"cli_path": cli(tmp_path), "ffmpeg_path": "/usr/bin/ffmpeg"}, "pack", False)
    job = VideoJob(
        "a cat",
        768,
        448,
        121,
        24,
        7,
        references=(
            VideoReference("first.png", b"first", 0, 1.0),
            VideoReference("last.png", b"last", 120, 0.5),
        ),
    )

    result = runner.run(job)

    command = commands[0]
    assert command[1] == "generate"
    assert command[command.index("-p") + 1] == "a cat"
    assert command[command.index("-H") + 1] == "448"
    assert command[command.index("-W") + 1] == "768"
    assert command[command.index("-f") + 1] == "121"
    assert command[command.index("--frame-rate") + 1] == "24"
    assert command[command.index("--model") + 1] == "pack"
    assert command[command.index("--seed") + 1] == "7"
    assert "--distilled" in command
    images = [index for index, argument in enumerate(command) if argument == "--image"]
    assert len(images) == 2
    assert command[images[0] + 2 : images[0] + 4] == ["0", "1"]
    assert command[images[1] + 2 : images[1] + 4] == ["120", "0.5"]
    assert not Path(command[images[0] + 1]).exists()
    assert result.mp4 == b"mp4 bytes"
    assert (result.width, result.height, result.num_frames, result.frame_rate, result.seed) == (768, 448, 121, 24, 7)


def test_a_model_without_an_enhancer_drops_the_flag_the_job_carries(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    job = VideoJob("a cat", 384, 384, 121, 24, 7, enhance=True)

    MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", False).run(job)
    MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", True).run(job)

    assert "--enhance-prompt" not in commands[0]
    assert "--enhance-prompt" in commands[1]


def test_a_job_without_a_seed_leaves_the_port_to_pick_one(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)

    MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", False).run(VideoJob("a cat", 384, 384, 121, 24, None))

    assert "--seed" not in commands[0]


def test_a_track_enters_the_audio_task_and_is_padded_to_the_clip(tmp_path, monkeypatch):
    commands = []
    ffmpeg_calls = []
    capture_execute(monkeypatch, commands)

    def fake_process(command, **options):
        ffmpeg_calls.append((command, options))
        Path(command[-1]).write_bytes(b"padded wav")
        return subprocess.CompletedProcess(command, 0)

    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("")
    runner = MlxVideoRunner(
        {"cli_path": cli(tmp_path), "ffmpeg_path": str(ffmpeg)},
        "pack",
        False,
        process_runner=fake_process,
    )
    job = VideoJob("she speaks", 384, 384, 121, 24, 7, audio=VideoAudio(b"wav bytes", "voice.wav"))

    runner.run(job)

    command = commands[0]
    assert command[1] == "a2v"
    assert command[command.index("--audio") + 1].endswith("padded.wav")
    assert "--distilled" not in command
    ffmpeg, options = ffmpeg_calls[0]
    assert ffmpeg[0] == str(tmp_path / "ffmpeg")
    assert ffmpeg[ffmpeg.index("-i") + 1].endswith("source.wav")
    assert ffmpeg[-1].endswith("padded.wav")
    assert ffmpeg.index("-i") < ffmpeg.index("-af") < ffmpeg.index("-t")
    assert ffmpeg[ffmpeg.index("-af") + 1] == "apad"
    assert ffmpeg[ffmpeg.index("-t") + 1] == "5.142"
    assert ffmpeg[ffmpeg.index("-ac") + 1] == "2"
    assert options["capture_output"] is True


def test_a_track_that_ffmpeg_cannot_read_is_named(tmp_path, monkeypatch):
    capture_execute(monkeypatch, [])

    def fake_process(command, **options):
        return subprocess.CompletedProcess(command, 1, stderr=b"noise\nInvalid data found")

    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("")
    runner = MlxVideoRunner(
        {"cli_path": cli(tmp_path), "ffmpeg_path": str(ffmpeg)},
        "pack",
        False,
        process_runner=fake_process,
    )

    with pytest.raises(StudioError, match="Invalid data found"):
        runner.run(VideoJob("she speaks", 384, 384, 121, 24, 7, audio=VideoAudio(b"junk", "voice.wav")))


def test_a_missing_port_executable_says_which_setting_to_fill(tmp_path):
    runner = MlxVideoRunner({}, "pack", False)

    with pytest.raises(StudioError, match="cli_path"):
        runner.run(VideoJob("a cat", 384, 384, 121, 24, 7))


def test_a_missing_ffmpeg_says_which_setting_to_fill(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", False)

    with pytest.raises(StudioError, match="ffmpeg_path"):
        runner.run(VideoJob("she speaks", 384, 384, 121, 24, 7, audio=VideoAudio(b"wav", "voice.wav")))


def test_a_bare_executable_name_is_resolved_on_path(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/local/bin/{name}")
    runner = MlxVideoRunner({"cli_path": "ltx-2-mlx"}, "pack", False)

    assert runner._checked("ltx-2-mlx", "missing") == "/usr/local/bin/ltx-2-mlx"


def test_execute_reports_each_counter_once():
    reports = []
    command = [
        sys.executable,
        "-c",
        "import sys; "
        "sys.stderr.write('Denoising:  25%|##| 2/8 [00:01<00:02]\\r'); "
        "sys.stderr.write('Denoising:  25%|##| 2/8 [00:01<00:02]\\r'); "
        "sys.stderr.write('Denoising:  50%|####| 4/8 [00:02<00:02]\\r'); "
        "sys.stderr.flush()",
    ]

    MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(
        command, lambda step, total, phase: reports.append((step, total, phase))
    )

    assert reports == [(2, 8, 1), (4, 8, 1)]


def test_a_dying_port_reports_its_last_lines():
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('RuntimeError: MPS out of memory\\n'); raise SystemExit(2)",
    ]

    with pytest.raises(StudioError, match="failed with exit status 2") as failure:
        MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(command, None)

    assert "MPS out of memory" in str(failure.value)


def test_a_silent_death_says_nothing():
    command = [sys.executable, "-c", "raise SystemExit(3)"]

    with pytest.raises(StudioError, match="exit status 3 and said nothing"):
        MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(command, None)


def test_execute_stops_the_child_when_cancelled():
    command = [sys.executable, "-c", "import time; time.sleep(30)"]

    with pytest.raises(Cancelled):
        MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(command, None, lambda: True)


def test_stop_process_leaves_a_child_that_already_exited():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()

    _stop_process(process)


def test_stop_process_ignores_a_process_that_is_already_gone():
    class Gone:
        def poll(self):
            return None

        def terminate(self):
            raise ProcessLookupError

    _stop_process(cast(Any, Gone()))


def test_stop_process_kills_a_child_that_ignores_terminate():
    class Stubborn:
        def __init__(self):
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("child", timeout)
            return 0

        def kill(self):
            self.killed = True

    child = Stubborn()

    _stop_process(cast(Any, child))

    assert child.killed is True


def test_the_timeout_names_the_hour(monkeypatch):
    monkeypatch.setattr(mlx_video_runner, "RUN_TIMEOUT_SECONDS", 0.01)
    command = [sys.executable, "-c", "import time; time.sleep(30)"]

    with pytest.raises(StudioError, match="timed out after one hour"):
        MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(command, None)


def test_a_run_that_writes_no_mp4_is_named(tmp_path, monkeypatch):
    def no_output(self, command, progress=None, cancelled=None):
        return None

    monkeypatch.setattr(MlxVideoRunner, "_execute", no_output)

    with pytest.raises(StudioError, match="did not write an MP4"):
        MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", False).run(VideoJob("a cat", 384, 384, 121, 24, 7))


def test_a_configured_binary_that_is_missing_is_named(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    runner = MlxVideoRunner({"cli_path": "not-here"}, "pack", False)

    with pytest.raises(StudioError, match="not-here"):
        runner._checked("not-here", "not-here")


def test_a_cancel_that_lands_after_the_child_exits_is_raised():
    calls = []

    def cancelled():
        calls.append(1)
        return len(calls) > 1

    with pytest.raises(Cancelled):
        MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute([sys.executable, "-c", "pass"], None, cancelled)


def test_a_two_stage_pack_builds_keyframes_on_the_two_stage_path(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", True, keyframe_two_stage=True)
    references = (VideoReference("first.png", b"first", 0, 1.0),)

    runner.run(VideoJob("a room", 384, 384, 121, 24, 7, references=references))
    runner.run(VideoJob("a room", 384, 384, 121, 24, 7))

    assert "--two-stage" in commands[0]
    assert "--distilled" not in commands[0]
    assert "--distilled" in commands[1]


def test_the_one_stage_pack_keeps_the_distilled_path_with_keyframes(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", False, keyframe_two_stage=False)

    runner.run(VideoJob("a room", 384, 384, 121, 24, 7, references=(VideoReference("a.png", b"a", 0, 1.0),)))

    assert "--distilled" in commands[0]
    assert "--two-stage" not in commands[0]
