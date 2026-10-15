import subprocess
import sys
from pathlib import Path

import pytest

from studio.l1_entities.errors import StudioError
from studio.l1_entities.video_job import VideoJob, VideoReference
from studio.l4_frameworks_and_drivers.ltx25_runner import Ltx25Runner

FILES = (
    "diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors",
    "text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
    "vae/ltx-2.5-video-vae-bf16.safetensors",
    "vae/ltx-2.5-audio-vae-bf16.safetensors",
    "model_patches/ltx-2.5-duration-head-bf16.safetensors",
    "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
)


def weights(root):
    for relative_path in FILES:
        model_file = root / relative_path
        model_file.parent.mkdir(parents=True, exist_ok=True)
        model_file.write_bytes(b"local model placeholder")


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


def test_runner_refuses_to_download_missing_local_weights(tmp_path):
    with pytest.raises(StudioError, match="local weights are missing"):
        Ltx25Runner("python", tmp_path / "missing").run(job())


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
        assert command[0] == str(Path(sys.executable).resolve())
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4")

    result = Ltx25Runner(sys.executable, model_dir, process_runner=fake_process).run(job())

    assert result.mp4 == b"mp4"


def test_runner_reports_incomplete_local_weights(tmp_path):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()

    with pytest.raises(StudioError, match="local weights are incomplete"):
        Ltx25Runner("python", model_dir).run(job())


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
