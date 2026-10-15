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


def test_default_downloader_requests_official_files_from_hugging_face(tmp_path, monkeypatch):
    model_dir = tmp_path / "ltx-models"
    downloads = []

    def fake_download(**options):
        downloads.append(options)
        weights(options["local_dir"])

    def fake_process(command, **options):
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4")

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_download)

    Ltx25Runner("python", model_dir, process_runner=fake_process).run(job())

    assert downloads == [
        {
            "repo_id": "Lightricks/LTX-2.5",
            "allow_patterns": list(FILES),
            "local_dir": model_dir,
        }
    ]


def test_runner_reports_model_download_failure(tmp_path, monkeypatch):
    def fail_download(**_options):
        raise RuntimeError("access denied")

    monkeypatch.setattr("huggingface_hub.snapshot_download", fail_download)
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
        assert command[0] == str(Path(sys.executable).resolve())
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4")

    result = Ltx25Runner(sys.executable, model_dir, process_runner=fake_process).run(job())

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
