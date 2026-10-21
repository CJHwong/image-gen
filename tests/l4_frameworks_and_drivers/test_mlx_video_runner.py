import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

import pytest

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.video_job import VideoAudio, VideoEdit, VideoJob, VideoReference
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
    assert command[command.index("--stage1-steps") + 1] == "8"
    assert command[command.index("--stage2-steps") + 1] == "3"
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
    assert command[command.index("--stage1-steps") + 1] == "30"
    assert command[command.index("--stage2-steps") + 1] == "3"
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
        "--stage1-steps",
        "8",
        "--stage2-steps",
        "3",
    ]

    MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(
        command, lambda step, total, phase: reports.append((step, total, phase))
    )

    assert reports == [(2, 11, 1), (4, 11, 1)]


@pytest.mark.parametrize("stages", [(8, 3), (30, 3), (8, 0)])
def test_progress_combines_stages_and_ignores_loading_bars(stages):
    reports = []
    first, second = stages
    records = ["Loading shards: 100%|#| 28/28 [00:01]\r"]
    for phase, total in enumerate(filter(None, stages)):
        description = "Denoising" if phase else "Denoising (guided)" if total == 30 else "Denoising (ancestral)"
        records.extend(f"{description}: 0%|#| {step}/{total} [00:01]\r" for step in range(total + 1))
        records.append(f"{description}: 100%|#| {total}/{total} [00:01]\n")
        records.append("Loading shards: 100%|#| 28/28 [00:01]\r")
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write(" + repr("".join(records)) + ")",
        "--stage1-steps",
        str(first),
        "--stage2-steps",
        str(second),
    ]

    MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(
        command, lambda step, total, phase: reports.append((step, total, phase))
    )

    assert [(step, total) for step, total, _phase in reports] == [
        (step, first + second) for step in range(first + second + 1)
    ]
    assert reports[-1][2] == (2 if second else 1)


def test_progress_retains_a_counter_split_between_pipe_reads():
    reports = []
    command = [
        sys.executable,
        "-c",
        "import sys,time; sys.stderr.write('Denoising: 25%|#| 2/'); sys.stderr.flush(); "
        "time.sleep(0.1); sys.stderr.write('8 [00:01]'); sys.stderr.flush()",
        "--stage1-steps",
        "8",
        "--stage2-steps",
        "3",
    ]

    MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(
        command, lambda step, total, phase: reports.append((step, total, phase))
    )

    assert reports == [(2, 11, 1)]


@pytest.mark.parametrize("stages", [(8, 3), (30, 3), (8, 0), (3, 3)])
def test_real_sampler_closes_below_total_and_decoder_loading_finishes_denoising(stages):
    reports = []
    records = []
    for total in filter(None, stages):
        records.extend(f"Denoising (ancestral): 0%|#| {step}/{total} [00:01]\r" for step in range(total))
        records.append(f"Denoising (ancestral): 88%|#| {total - 1}/{total} [00:01]\n")
    records.extend(
        [
            "[Loading decoders (VAE + audio + vocoder)] ...\n",
            "[Loading decoders (VAE + audio + vocoder)] done in 2.0s\n",
            "[Decoding video + audio + muxing] ...\n",
        ]
    )
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write(" + repr("".join(records)) + ")",
        "--stage1-steps",
        str(stages[0]),
        "--stage2-steps",
        str(stages[1]),
    ]

    MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(
        command, lambda step, total, phase: reports.append((step, total, phase))
    )

    total_steps = sum(stages)
    assert [(step, total) for step, total, _phase in reports] == [
        (step, total_steps) for step in range(total_steps + 1)
    ]
    assert reports[-1][2] == (2 if stages[1] else 1)


def test_decoder_phase_split_across_reads_marks_denoising_complete():
    reports = []
    command = [
        sys.executable,
        "-c",
        "import sys,time; sys.stderr.write('[Decoding video '); sys.stderr.flush(); time.sleep(0.1); "
        "sys.stderr.write('(--no-audio)] ...'); sys.stderr.flush()",
        "--stage1-steps",
        "8",
        "--stage2-steps",
        "0",
    ]

    MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(
        command, lambda step, total, phase: reports.append((step, total, phase))
    )

    assert reports == [(8, 8, 1)]


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


def test_a_gated_pack_names_the_login_step():
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('huggingface_hub.errors.GatedRepoError: 401 Client Error. "
        "Cannot access gated repo\\n'); raise SystemExit(1)",
    ]

    with pytest.raises(StudioError) as failure:
        MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(command, None)

    message = str(failure.value)
    assert "gated repo" in message
    assert "hf auth login" in message
    # The tail stays, because the status and the class name are what a report needs.
    assert "GatedRepoError" in message


def test_an_unknown_pack_names_the_setting():
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('huggingface_hub.errors.RepositoryNotFoundError: 404\\n'); raise SystemExit(1)",
    ]

    with pytest.raises(StudioError) as failure:
        MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(command, None)

    assert "[mlx_video] in studio.toml" in str(failure.value)


def test_an_unreachable_registry_names_the_network():
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('httpx.ConnectError: MaxRetryError while resolving\\n'); raise SystemExit(1)",
    ]

    with pytest.raises(StudioError) as failure:
        MlxVideoRunner({"cli_path": "x"}, "pack", False)._execute(command, None)

    assert "Check the network" in str(failure.value)


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
    assert commands[0][commands[0].index("--stage1-steps") + 1] == "30"
    assert commands[0][commands[0].index("--stage2-steps") + 1] == "3"
    assert "--distilled" in commands[1]


def test_the_one_stage_pack_keeps_the_distilled_path_with_keyframes(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", False, keyframe_two_stage=False)

    runner.run(VideoJob("a room", 384, 384, 121, 24, 7, references=(VideoReference("a.png", b"a", 0, 1.0),)))

    assert "--distilled" in commands[0]
    assert "--two-stage" not in commands[0]


def test_an_effect_job_builds_the_single_stage_ic_lora_command(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    loras = tmp_path / "loras"
    loras.mkdir()
    (loras / "effect.safetensors").write_bytes(b"weights")
    runner = MlxVideoRunner(
        {"cli_path": cli(tmp_path), "lora_dir": str(loras)},
        "pack",
        False,
    )
    job = VideoJob(
        "relight it",
        384,
        384,
        121,
        24,
        7,
        edit=VideoEdit("day-to-night", 1.0, "effect.safetensors", b"clip bytes", "clip.mp4"),
    )

    runner.run(job)

    command = commands[0]
    assert command[1] == "ic-lora"
    assert "--single-stage" in command
    assert "--distilled" not in command
    assert command[command.index("--stage1-steps") + 1] == "8"
    assert command[command.index("--stage2-steps") + 1] == "0"
    assert command[command.index("--lora") + 1] == str(loras / "effect.safetensors")
    assert command[command.index("--lora") + 2] == "1"
    assert command[command.index("--video-conditioning") + 2] == "1.0"
    assert Path(command[command.index("--video-conditioning") + 1]).suffix == ".mp4"
    assert command[command.index("-H") + 1] == "384"
    assert "--seed" in command


def test_a_missing_effect_is_fetched_from_an_unrelated_working_directory(tmp_path, monkeypatch):
    commands = []
    real_execute = MlxVideoRunner._execute

    def execute(self, command, progress=None, cancelled=None):
        if command[1] == "-c":
            return real_execute(self, command, progress, cancelled)
        commands.append(command)
        Path(command[command.index("-o") + 1]).write_bytes(b"mp4 bytes")

    monkeypatch.setattr(MlxVideoRunner, "_execute", execute)
    (tmp_path / "huggingface_hub.py").write_text(
        "from pathlib import Path\n"
        "def hf_hub_download(repo_id, filename, local_dir):\n"
        "    assert repo_id == 'Lightricks/LTX-2.5-22b-IC-LoRA-Deblur'\n"
        "    target = Path(local_dir) / filename\n"
        "    target.write_bytes(b'weights')\n"
        "    return str(target)\n"
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    loras = tmp_path / "loras"
    runner = MlxVideoRunner(
        {"cli_path": cli(tmp_path), "lora_dir": str(loras), "fetch_loras": True},
        "pack",
        False,
    )
    job = VideoJob(
        "sharpen",
        960,
        544,
        121,
        24,
        7,
        edit=VideoEdit("deblur", 1.0, "effect.safetensors", b"clip bytes", "clip.mp4"),
    )

    result = runner.run(job)

    assert (loras / "effect.safetensors").read_bytes() == b"weights"
    assert commands[0][commands[0].index("--lora") + 1] == str(loras / "effect.safetensors")
    assert result.mp4 == b"mp4 bytes"


def test_a_missing_effect_is_refused_when_the_setting_says_no(tmp_path):
    loras = tmp_path / "loras"
    loras.mkdir()
    runner = MlxVideoRunner(
        {"cli_path": cli(tmp_path), "lora_dir": str(loras), "fetch_loras": False},
        "pack",
        False,
    )
    job = VideoJob(
        "relight it",
        384,
        384,
        121,
        24,
        7,
        edit=VideoEdit("day-to-night", 1.0, "effect.safetensors", b"clip bytes", "clip.mp4"),
    )

    with pytest.raises(StudioError, match="fetch_loras"):
        runner.run(job)


def test_cancel_stops_a_download_before_the_engine_starts(tmp_path, monkeypatch):
    marker = tmp_path / "download.pid"
    (tmp_path / "huggingface_hub.py").write_text(
        "import os, time\n"
        "from pathlib import Path\n"
        "def hf_hub_download(**kwargs):\n"
        f"    Path({str(marker)!r}).write_text(str(os.getpid()))\n"
        "    time.sleep(30)\n"
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))

    def refuse_parent_download(**kwargs):
        raise RuntimeError("The download must run in a cancellable child.")

    monkeypatch.setattr("huggingface_hub.hf_hub_download", refuse_parent_download)
    runner = MlxVideoRunner(
        {"cli_path": cli(tmp_path), "lora_dir": str(tmp_path / "loras"), "fetch_loras": True},
        "pack",
        False,
    )
    job = VideoJob(
        "sharpen", 960, 544, 121, 24, 7, edit=VideoEdit("deblur", 1.0, "effect.safetensors", b"clip", "clip.mp4")
    )

    started = time.monotonic()
    with pytest.raises(Cancelled):
        runner.run(job, cancelled=marker.exists)

    assert time.monotonic() - started < 5
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)


def test_an_effect_without_its_weights_names_the_directory(tmp_path):
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", False)
    job = VideoJob(
        "relight it",
        384,
        384,
        121,
        24,
        7,
        edit=VideoEdit("day-to-night", 1.0, "effect.safetensors", b"clip", "clip.mp4"),
    )

    with pytest.raises(StudioError, match="lora_dir"):
        runner.run(job)


def test_an_effect_file_that_is_missing_is_named(tmp_path):
    loras = tmp_path / "loras"
    loras.mkdir()
    runner = MlxVideoRunner({"cli_path": cli(tmp_path), "lora_dir": str(loras)}, "pack", False)
    job = VideoJob(
        "relight it",
        384,
        384,
        121,
        24,
        7,
        edit=VideoEdit("day-to-night", 1.0, "effect.safetensors", b"clip", "clip.mp4"),
    )

    with pytest.raises(StudioError, match=r"effect\.safetensors"):
        runner.run(job)


def test_an_effect_job_without_a_seed_leaves_it_to_the_port(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    loras = tmp_path / "loras"
    loras.mkdir()
    (loras / "effect.safetensors").write_bytes(b"weights")
    runner = MlxVideoRunner({"cli_path": cli(tmp_path), "lora_dir": str(loras)}, "pack", False)
    job = VideoJob(
        "relight it",
        384,
        384,
        121,
        24,
        None,
        edit=VideoEdit("day-to-night", 1.0, "effect.safetensors", b"clip", "clip.mp4"),
    )

    runner.run(job)

    assert "--seed" not in commands[0]


def test_a_compatible_batch_uses_one_child_and_retains_each_clip(tmp_path, monkeypatch):
    import json

    from studio.l4_frameworks_and_drivers import mlx_video_batch as batch

    monkeypatch.setattr(batch, "physical_memory", lambda: 64 * 1024**3)
    executable = cli(tmp_path)
    (tmp_path / "python").write_text("")
    jobs = [VideoJob("a cat", 800, 752, 9, 24, 7), VideoJob("a dog", 800, 752, 9, 24, 8)]
    events = []
    calls = []

    def execute(self, command, progress, cancelled, consume=None, timeout_started=None):
        calls.append(command)
        assert consume is not None
        manifest = Path(command[-1])
        commands = json.loads(manifest.read_text())
        for index, arguments in enumerate(commands, 1):
            consume(f'STUDIO_BATCH:{{"event":"start","index":{index}}}\n')
            Path(arguments[arguments.index("-o") + 1]).write_bytes(str(index).encode())
            consume(f'STUDIO_BATCH:{{"event":"done","index":{index}}}\n')
            assert (manifest.parent / f"{index}.ack").exists()

    monkeypatch.setattr(MlxVideoRunner, "_execute", execute)
    runner = MlxVideoRunner({"cli_path": executable}, "dgrauet/ltx-2.5-mlx-q8", False)
    results = runner.run_batch(
        jobs,
        lambda index, result: events.append((index, result.mp4)),
        lambda index, total: events.append((index, total)),
        None,
        lambda: False,
    )
    assert len(calls) == 1
    assert calls[0][-2] == "offload"
    assert events == [(1, 2), (1, b"1"), (2, 2), (2, b"2")]
    assert [result.mp4 for result in results] == [b"1", b"2"]


def test_an_incompatible_batch_keeps_the_existing_single_run_path(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "another-model", False)
    jobs = [VideoJob("a cat", 384, 384, 121, 24, 7)] * 2
    retained = []
    assert (
        len(runner.run_batch(jobs, lambda *values: retained.append(values), lambda *_: None, None, lambda: False)) == 2
    )
    assert len(commands) == 2
    assert len(retained) == 2


def test_a_batch_cancel_before_its_first_item_never_starts_a_child(tmp_path):
    runner = MlxVideoRunner({}, "pack", False)
    with pytest.raises(Cancelled):
        runner.run_batch([VideoJob("cat", 800, 752, 9, 24, 7)], lambda *_: None, lambda *_: None, None, lambda: True)


def test_a_protocol_callback_failure_stops_the_real_waiting_child(tmp_path):
    runner = MlxVideoRunner({}, "pack", False)
    code = "import sys,time; print('marker', file=sys.stderr, flush=True); time.sleep(60)"

    def fail(text):
        raise StudioError("retention failed")

    started = time.monotonic()
    with pytest.raises(StudioError, match="retention failed"):
        runner._execute([sys.executable, "-c", code], None, consume=fail)
    assert time.monotonic() - started < 5


def test_a_batch_with_no_protocol_completion_fails(tmp_path, monkeypatch):
    from studio.l4_frameworks_and_drivers import mlx_video_batch as batch

    monkeypatch.setattr(batch, "physical_memory", lambda: 64 * 1024**3)
    executable = cli(tmp_path)
    (tmp_path / "python").write_text("")
    monkeypatch.setattr(MlxVideoRunner, "_execute", lambda *args: None)
    runner = MlxVideoRunner({"cli_path": executable}, "dgrauet/ltx-2.5-mlx-q8", False)
    with pytest.raises(StudioError, match="before every item"):
        runner.run_batch(
            [VideoJob("cat", 800, 752, 9, 24, 7)] * 2, lambda *_: None, lambda *_: None, None, lambda: False
        )


def test_a_sequential_batch_checks_cancel_between_items(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", False)
    with pytest.raises(Cancelled):
        runner.run_batch(
            [VideoJob("cat", 800, 752, 9, 24, 7)] * 2, lambda *_: None, lambda *_: None, None, lambda: bool(commands)
        )
    assert len(commands) == 1


def test_an_unconfigured_model_has_an_explicit_error():
    with pytest.raises(StudioError, match="Set the model"):
        MlxVideoRunner({}, "", False).run(VideoJob("cat", 800, 752, 9, 24, 7))


def cpu_batch_environment(tmp_path, monkeypatch):
    from studio.l4_frameworks_and_drivers import mlx_video_batch as batch

    monkeypatch.setattr(batch, "physical_memory", lambda: 64 * 1024**3)
    python = tmp_path / "python"
    python.symlink_to(sys.executable)
    from studio.l4_frameworks_and_drivers import mlx_video_batch as batch

    monkeypatch.setattr(batch, "physical_memory", lambda: 64 * 1024**3)
    executable = cli(tmp_path)
    engine = tmp_path / "ltx_pipelines_mlx"
    engine.mkdir()
    (engine / "__init__.py").write_text("")
    (engine / "distilled.py").write_text(
        "from types import SimpleNamespace\n"
        "class DistilledPipeline:\n"
        " def __init__(self,*args,**kwargs):\n"
        "  self.prompt_encoder=SimpleNamespace(encode=lambda prompt:(prompt,'audio'),free=lambda:None)\n"
        " def _stage1(self):pass\n def _upsample_latent(self):pass\n def _stage2(self):pass\n def _decode_and_save_video(self):pass\n"
    )
    (engine / "cli.py").write_text(
        "import sys\nfrom pathlib import Path\nimport ltx_pipelines_mlx.distilled as distilled\n"
        "def main():\n"
        " pipeline=distilled.DistilledPipeline('pack',low_memory=True)\n"
        " prompt=sys.argv[sys.argv.index('-p')+1]\n"
        " pipeline._load_text_encoder()\n"
        " assert pipeline._encode_text(prompt)[0]==prompt\n"
        " if prompt=='fail': raise RuntimeError('CPU child failure')\n"
        " print('Denoising: 0%| | 0/8 [x]\\r[Loading decoders (VAE)]',file=sys.stderr,flush=True)\n"
        " Path(sys.argv[sys.argv.index('-o')+1]).write_bytes(prompt.encode())\n"
    )
    mlx = tmp_path / "mlx"
    mlx.mkdir()
    (mlx / "__init__.py").write_text("")
    (mlx / "core.py").write_text("def eval(*args):pass\ndef set_cache_limit(value):pass\n")
    memory = tmp_path / "ltx_core_mlx" / "utils"
    memory.mkdir(parents=True)
    (memory.parent / "__init__.py").write_text("")
    (memory / "__init__.py").write_text("")
    (memory / "memory.py").write_text("def aggressive_cleanup():pass\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    return MlxVideoRunner({"cli_path": executable}, "dgrauet/ltx-2.5-mlx-q8", False)


@pytest.mark.parametrize("width,height,frames", [(800, 752, 9), (1920, 1088, 97), (1920, 1088, 49)])
def test_real_cpu_child_runs_the_batch_protocol_and_retains_distinct_outputs(
    tmp_path, monkeypatch, width, height, frames
):
    runner = cpu_batch_environment(tmp_path, monkeypatch)
    jobs = [VideoJob(prompt, width, height, frames, 24, seed) for seed, prompt in enumerate(["cat", "dog", "cup"])]
    completed = []
    started = []
    progress = []
    results = runner.run_batch(
        jobs,
        lambda *values: completed.append(values),
        lambda *values: started.append(values),
        lambda *values: progress.append(values),
        lambda: False,
    )
    assert [result.mp4 for result in results] == [b"cat", b"dog", b"cup"]
    assert [index for index, _ in completed] == [1, 2, 3]
    assert started == [(1, 3), (2, 3), (3, 3)]
    assert progress == [(0, 11, 1), (11, 11, 1)] * 3


@pytest.mark.parametrize("cancel", [False, True])
def test_real_cpu_batch_preserves_the_first_output_on_failure_or_cancel(tmp_path, monkeypatch, cancel):
    runner = cpu_batch_environment(tmp_path, monkeypatch)
    jobs = [VideoJob(prompt, 800, 752, 9, 24, 7) for prompt in ["cat", "fail"]]
    completed = []
    before = time.monotonic()
    with pytest.raises(Cancelled if cancel else StudioError):
        runner.run_batch(
            jobs, lambda *values: completed.append(values), lambda *_: None, None, lambda: cancel and bool(completed)
        )
    assert len(completed) == 1
    assert completed[0][1].mp4 == b"cat"
    assert time.monotonic() - before < 5


def test_sequential_configuration_keeps_batches_but_disables_reuse(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    runner = MlxVideoRunner({"cli_path": cli(tmp_path), "batch_policy": "sequential"}, "dgrauet/ltx-2.5-mlx-q8", False)
    jobs = [VideoJob("cat", 768, 768, 121, 24, 7)] * 2
    assert len(runner.run_batch(jobs, lambda *_: None, lambda *_: None, None, lambda: False)) == 2
    assert len(commands) == 2


def test_invalid_batch_policy_has_an_explicit_configuration_error():
    with pytest.raises(StudioError, match="batch_policy"):
        MlxVideoRunner({"batch_policy": "force"}, "pack", False)


def test_batch_timeout_resets_per_validated_item_not_per_process(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from studio.l4_frameworks_and_drivers import mlx_video_batch as batch

    runner = cpu_batch_environment(tmp_path, monkeypatch)
    clock = [100.0]
    fake_time = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr(mlx_video_runner, "time", fake_time)
    monkeypatch.setattr(batch, "time", fake_time)
    completed = []

    def retain(index, result):
        clock[0] += 2000  # Each clip < one hour; three clips > one hour.
        completed.append(result)

    jobs = [VideoJob(prompt, 800, 752, 9, 24, 7) for prompt in ("cat", "dog", "cup")]
    results = runner.run_batch(jobs, retain, lambda *_: None, None, lambda: False)
    assert len(results) == len(completed) == 3
    assert clock[0] == 6100


def test_batch_loading_still_has_a_timeout_before_the_first_validated_start(monkeypatch):
    monkeypatch.setattr(mlx_video_runner, "RUN_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(StudioError, match="timed out after one hour"):
        MlxVideoRunner({}, "pack", False)._execute(
            [sys.executable, "-c", "import time; time.sleep(30)"], None, timeout_started=lambda: None
        )


def test_audio_generation_uses_native_enhancement_before_the_audio_pipeline(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    executable = cli(tmp_path)
    (tmp_path / "python").write_text("")
    runner = MlxVideoRunner({"cli_path": executable}, "pack-25", True)
    monkeypatch.setattr(runner, "_write_audio", lambda job, root: root / "audio.wav")
    job = VideoJob("She speaks.", 384, 384, 9, 24, 7, enhance=True, audio=VideoAudio(b"wav", "voice.wav"))
    runner.run(job)
    command = commands[0]
    assert command[0] == str(tmp_path / "python")
    assert command[1].endswith("mlx_video_generation_child.py")
    assert command[2] == "a2v" and "--enhance-prompt" not in command
    assert command[command.index("-p") + 1] == job.prompt


@pytest.mark.parametrize(
    "policy,model,width,height,expected",
    [
        ("auto", "dgrauet/ltx-2.5-mlx-q8", 1920, 1088, "offload"),
        ("enhance_only", "dgrauet/ltx-2.5-mlx-q8", 1920, 1088, "sequential"),
        ("auto", "dgrauet/ltx-2.3-mlx-q8", 384, 384, "sequential"),
    ],
)
def test_enhanced_batches_finish_preparation_before_video_reuse(
    tmp_path, monkeypatch, policy, model, width, height, expected
):
    import json

    from studio.l4_frameworks_and_drivers import mlx_video_batch

    monkeypatch.setattr(mlx_video_batch, "physical_memory", lambda: 64 * 1024**3)
    (tmp_path / "python").write_text("")
    calls = []

    def execute(self, command, progress=None, cancelled=None, consume=None, timeout_started=None):
        calls.append(command)
        manifest = Path(command[-1])
        commands = json.loads(manifest.read_text())
        if command[1].endswith("mlx_video_batch_enhancement.py"):
            assert consume is None
            for item in commands:
                item[item.index("-p") + 1] += " enhanced"
                item.remove("--enhance-prompt")
            manifest.write_text(json.dumps(commands))
            return
        assert len(calls) == 2 and command[-2] == expected
        assert consume is not None
        for index, item in enumerate(commands, 1):
            assert "--enhance-prompt" not in item
            consume(f'STUDIO_BATCH:{{"event":"start","index":{index}}}\n')
            Path(item[item.index("-o") + 1]).write_bytes(item[item.index("-p") + 1].encode())
            consume(f'STUDIO_BATCH:{{"event":"done","index":{index}}}\n')

    monkeypatch.setattr(MlxVideoRunner, "_execute", execute)
    runner = MlxVideoRunner({"cli_path": cli(tmp_path), "batch_policy": policy}, model, True)
    jobs = [VideoJob(prompt, width, height, 49, 24, 7, enhance=True) for prompt in ["cat", "dog"]]
    starts = []
    results = runner.run_batch(jobs, lambda *_: None, lambda *args: starts.append(args), None, lambda: False)
    assert len(calls) == 2 and [result.mp4 for result in results] == [b"cat enhanced", b"dog enhanced"]
    assert starts == [(1, 2), (2, 2)]


def test_enhancement_failure_never_starts_video_or_claims_an_item(tmp_path, monkeypatch):
    (tmp_path / "python").write_text("")
    calls = []

    def execute(self, command, *args):
        calls.append(command)
        raise StudioError("enhancer failed")

    monkeypatch.setattr(MlxVideoRunner, "_execute", execute)
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", True)
    events = []
    with pytest.raises(StudioError, match="enhancer failed"):
        runner.run_batch(
            [VideoJob("cat", 384, 384, 9, 24, 7, enhance=True)] * 2,
            lambda *args: events.append(args),
            lambda *args: events.append(args),
            None,
            lambda: False,
        )
    assert len(calls) == 1 and calls[0][1].endswith("mlx_video_batch_enhancement.py")
    assert not events


def test_preparation_checks_cancellation_before_media_work(tmp_path):
    (tmp_path / "python").write_text("")
    calls = iter([False, True])
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", True)
    with pytest.raises(Cancelled):
        runner.run_batch(
            [VideoJob("cat", 384, 384, 9, 24, 7, enhance=True)] * 2,
            lambda *_: None,
            lambda *_: None,
            None,
            lambda: next(calls),
        )


def test_an_enhanced_batch_checks_missing_model_before_starting(tmp_path):
    (tmp_path / "python").write_text("")
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "", True)
    with pytest.raises(StudioError, match="Set the model"):
        runner.run_batch(
            [VideoJob("cat", 384, 384, 9, 24, 7, enhance=True)] * 2,
            lambda *_: None,
            lambda *_: None,
            None,
            lambda: False,
        )


def test_audio_batch_marks_native_enhancement_before_parsing_a2v(tmp_path, monkeypatch):
    import json

    (tmp_path / "python").write_text("")
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", True)
    monkeypatch.setattr(runner, "_write_audio", lambda job, root: root / "ref.wav" if job.audio else None)
    seen = []

    def execute(self, command, *args):
        seen.extend(json.loads(Path(command[-1]).read_text()))
        raise StudioError("enough")

    monkeypatch.setattr(MlxVideoRunner, "_execute", execute)
    jobs = [
        VideoJob("cat", 384, 384, 9, 24, 7, enhance=flag, audio=VideoAudio(b"a", "ref.wav")) for flag in [True, False]
    ]
    with pytest.raises(StudioError, match="enough"):
        runner.run_batch(jobs, lambda *_: None, lambda *_: None, None, lambda: False)
    assert [item[1] for item in seen] == ["a2v", "a2v"]
    assert ["--enhance-prompt" in item for item in seen] == [True, False]


def test_mixed_edit_batch_keeps_per_item_enhancement_and_effect_handling(tmp_path, monkeypatch):
    from studio.l1_entities.video_job import VideoResult

    (tmp_path / "python").write_text("")
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "pack", True)
    jobs = [
        VideoJob("cat", 384, 384, 9, 24, 7, enhance=True),
        VideoJob("effect", 384, 384, 9, 24, 8, edit=cast(Any, object())),
    ]
    calls = []

    def run(job, *args):
        calls.append(job)
        return VideoResult(b"mp4", job.width, job.height, job.num_frames, job.frame_rate, job.seed)

    monkeypatch.setattr(runner, "run", run)
    runner.run_batch(jobs, lambda *_: None, lambda *_: None, None, lambda: False)
    assert calls == jobs


def enable_cpu_enhancement(tmp_path):
    encoder = tmp_path / "ltx_core_mlx/text_encoders/gemma/encoders"
    encoder.mkdir(parents=True)
    for folder in [encoder, encoder.parent, encoder.parent.parent]:
        (folder / "__init__.py").write_text("")
    (encoder / "base_encoder.py").write_text(
        "import os,time,sys\nfrom pathlib import Path\n"
        "class GemmaLanguageModel:\n"
        " def load(self,path):\n"
        f"  with Path({str(tmp_path / 'enhancer-loads')!r}).open('a') as f:f.write(str(os.getpid())+'\\n')\n"
        "  print('enhancer loaded',file=sys.stderr,flush=True)\n"
        "  if os.environ.get('TEST_PAUSE_ENHANCER'):time.sleep(60)\n"
        " def enhance_t2v(self,prompt,seed):return 'enhanced '+prompt\n"
    )
    cli = tmp_path / "ltx_pipelines_mlx/cli.py"
    cli.write_text(
        cli.read_text() + "\nimport argparse\n"
        "def _build_parser():\n"
        " p=argparse.ArgumentParser()\n"
        " p.add_argument('command');p.add_argument('-p',dest='prompt');p.add_argument('--seed',type=int,default=-1);p.add_argument('--gemma',default='gemma')\n"
        " original=p.parse_known_args\n"
        " p.parse_args=lambda args:original(args)[0]\n"
        " return p\n"
        "def _guard_enhance_not_gemma4(path):pass\n"
    )


def test_real_cpu_enhancement_process_exits_before_the_prepared_video_child(tmp_path, monkeypatch):
    runner = cpu_batch_environment(tmp_path, monkeypatch)
    enable_cpu_enhancement(tmp_path)
    runner._enhances = True
    jobs = [VideoJob(prompt, 800, 752, 9, 24, 7, enhance=True) for prompt in ["cat", "dog"]]
    results = runner.run_batch(jobs, lambda *_: None, lambda *_: None, None, lambda: False)
    assert [result.mp4 for result in results] == [b"enhanced cat", b"enhanced dog"]
    assert len((tmp_path / "enhancer-loads").read_text().splitlines()) == 1


def test_cancel_during_real_cpu_enhancement_stops_before_any_video_item(tmp_path, monkeypatch):
    runner = cpu_batch_environment(tmp_path, monkeypatch)
    enable_cpu_enhancement(tmp_path)
    runner._enhances = True
    monkeypatch.setenv("TEST_PAUSE_ENHANCER", "1")
    events = []
    start = time.monotonic()
    with pytest.raises(Cancelled):
        runner.run_batch(
            [VideoJob("cat", 800, 752, 9, 24, 7, enhance=True)] * 2,
            lambda *args: events.append(args),
            lambda *args: events.append(args),
            None,
            lambda: (tmp_path / "enhancer-loads").exists(),
        )
    assert time.monotonic() - start < 5
    assert events == []
    pid = int((tmp_path / "enhancer-loads").read_text().strip())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.live
def test_mlx_enhanced_batch_live(tmp_path):
    """Use the product runner and real weights; a separate API check covers high-res reuse."""
    import json
    import socket
    import tomllib

    settings = tomllib.loads(Path("studio.toml").read_text())["mlx_video"]
    settings["cli_path"] = str(Path(settings["cli_path"]).expanduser())
    if not Path(settings["cli_path"]).is_file():
        pytest.skip("Install the configured LTX MLX environment first.")
    with socket.socket() as connection:
        assert connection.connect_ex(("127.0.0.1", 8765)) != 0, "Stop the user Studio server before a live GPU check."
    processes = subprocess.check_output(["ps", "-axo", "pid,command"]).decode()
    assert not any(
        any(
            name in line
            for name in [
                "/bin/ltx-2-mlx",
                "mlx_video_batch_child.py",
                "mlx_video_batch_enhancement.py",
                "/auk_child.py",
                "/drama3_child.py",
            ]
        )
        for line in processes.splitlines()
    ), "Another model process owns the GPU."
    token = Path("/tmp/image-gen-gpu-owner.token")
    try:
        owner = token.open("x")
    except FileExistsError:
        pytest.skip("The GPU has an existing owner; do not reclaim its token.")
    try:
        with owner:
            owner.write(str(os.getpid()))
        runner = MlxVideoRunner(settings, settings["model_ltx25"], True)
        starts = []
        retained = []
        jobs = [
            VideoJob(prompt, 384, 384, 9, 24, seed, enhance=True)
            for prompt, seed in [
                ("A red paper boat floats on a calm pond.", 7),
                ("A blue teapot rests on a wooden table.", 8),
            ]
        ]
        results = runner.run_batch(
            jobs,
            lambda index, result: retained.append((index, result)),
            lambda *args: starts.append(args),
            None,
            lambda: False,
        )
        assert starts == [(1, 2), (2, 2)] and [index for index, _ in retained] == [1, 2]
        assert [result.seed for result in results] == [7, 8]
        assert results[0].mp4 != results[1].mp4
        for index, result in enumerate(results):
            path = tmp_path / f"{index}.mp4"
            path.write_bytes(result.mp4)
            ffmpeg = Path(settings["ffmpeg_path"])
            subprocess.run(
                [str(ffmpeg), "-v", "error", "-i", str(path), "-f", "null", "-"], check=True, capture_output=True
            )
            info = json.loads(
                subprocess.check_output(
                    [
                        str(ffmpeg.with_name("ffprobe")),
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=width,height,nb_frames",
                        "-of",
                        "json",
                        str(path),
                    ]
                )
            )["streams"][0]
            assert info == {"width": 384, "height": 384, "nb_frames": "9"}
    finally:
        token.unlink()


def test_auto_avoids_the_measured_short_high_resolution_regression(tmp_path, monkeypatch):
    commands = []
    capture_execute(monkeypatch, commands)
    (tmp_path / "python").write_text("")
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "dgrauet/ltx-2.5-mlx-q8", True)
    jobs = [VideoJob(prompt, 1920, 1088, 17, 24, 7, enhance=True) for prompt in ["cat", "dog"]]
    results = runner.run_batch(jobs, lambda *_: None, lambda *_: None, None, lambda: False)
    assert len(results) == 2 and len(commands) == 2
    assert all("--enhance-prompt" in command and command[1] == "generate" for command in commands)


def test_effectively_unenhanced_jobs_keep_their_existing_reuse_path(tmp_path, monkeypatch):
    from studio.l4_frameworks_and_drivers import mlx_video_batch

    monkeypatch.setattr(mlx_video_batch, "physical_memory", lambda: 64 * 1024**3)
    (tmp_path / "python").write_text("")
    runner = MlxVideoRunner({"cli_path": cli(tmp_path)}, "dgrauet/ltx-2.5-mlx-q8", False)
    selected = []
    monkeypatch.setattr(runner, "_execute", lambda *args: selected.append("reuse"))
    monkeypatch.setattr(runner, "_sequential_batch", lambda *args: selected.append("sequential") or [])
    with pytest.raises(StudioError, match="before every item"):
        runner.run_batch(
            [VideoJob("cat", 1920, 1088, 17, 24, 7, enhance=True)] * 2,
            lambda *_: None,
            lambda *_: None,
            None,
            lambda: False,
        )
    assert selected == ["reuse"]
