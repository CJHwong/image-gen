import contextlib
import json
import subprocess
import sys
import time
import types
from pathlib import Path
from typing import cast

import pytest

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.video_job import VideoAudio, VideoEdit, VideoJob, VideoReference
from studio.l4_frameworks_and_drivers.ltx25_runner import PROGRESS_WRAPPER, Ltx25Runner, _stop_process

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
AUDIO_FILES = (
    "diffusion_models/ltx-2.5-22b-dev-transformer-bf16.safetensors",
    "loras/ltx-2.5-22b-distilled-lora-450-bf16.safetensors",
)


def weights(root):
    for relative_path in FILES:
        model_file = root / relative_path
        model_file.parent.mkdir(parents=True, exist_ok=True)
        model_file.write_bytes(b"local model placeholder")


def audio_weights(root):
    for relative_path in AUDIO_FILES:
        model_file = root / relative_path
        model_file.parent.mkdir(parents=True, exist_ok=True)
        model_file.write_bytes(b"local model placeholder")


def audio_job(references=()):
    return VideoJob(
        "A kite rises to a beat",
        960,
        544,
        145,
        24,
        42,
        references,
        audio=VideoAudio(b"RIFF\x24\x00\x00\x00WAVEfmt ", "theme.wav"),
    )


def live_runtime_ready():
    return LIVE_PYTHON_PATH.is_file() and all((LIVE_MODEL_DIR / relative_path).is_file() for relative_path in FILES)


def job(references=()):
    return VideoJob("A kite rises above the beach", 960, 544, 145, 24, 42, references)


def test_a_run_that_asks_for_the_enhancer_names_its_weights(tmp_path):
    """The video model's own prompt enhancer is a second Gemma with its own directory, and
    the pipeline wants that directory named. A run carries the switch, so only a run that
    asked for it passes the two flags."""
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    enhancer = tmp_path / "gemma-4-E2B-it"
    enhancer.mkdir()
    calls = []

    def fake_process(command, **options):
        calls.append(command)
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4 bytes")

    runner = Ltx25Runner("python", model_dir, process_runner=fake_process, prompt_enhancer_root=enhancer)
    runner.run(VideoJob("A kite rises", 960, 544, 145, 24, 42, (), enhance=True))
    runner.run(job())

    with_enhancer, without = calls
    assert "--enhance-prompt" in with_enhancer
    assert with_enhancer[with_enhancer.index("--prompt-enhancer-gemma-root") + 1] == str(enhancer)
    assert "--enhance-prompt" not in without
    assert "--prompt-enhancer-gemma-root" not in without


def test_a_run_that_asks_for_the_enhancer_without_its_weights_says_how_to_get_them(tmp_path):
    """The weights come from their own repository and this runner fetches one model only, so
    a switch with nothing on disk has to fail with a line a person can act on rather than
    inside the pipeline over a path."""
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    runner = Ltx25Runner("python", model_dir, prompt_enhancer_root=tmp_path / "not-downloaded")

    with pytest.raises(StudioError, match="prompt enhancer and its weights are not on disk"):
        runner.run(VideoJob("A kite rises", 960, 544, 145, 24, 42, (), enhance=True))


def normalize_to_wav(_python, _source, target, _seconds):
    """Stand in for the engine's decoder, which writes stereo PCM from the track."""
    target.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")


def test_a_run_with_a_track_enters_the_audio_pipeline_with_its_own_weights(tmp_path, monkeypatch):
    """The audio pipeline runs the full model in stage 1 and refines with a distilled LoRA,
    so it takes two files the drawing pipeline never opens. The form's length stays the
    driver: the command carries --num-frames and the pipeline trims the track to it."""
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    audio_weights(model_dir)
    monkeypatch.setattr(Ltx25Runner, "_normalize_audio", staticmethod(normalize_to_wav))
    calls = []

    def fake_process(command, **options):
        calls.append(command)
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4 with a track")

    result = Ltx25Runner("python", model_dir, process_runner=fake_process).run(audio_job())

    command = calls[0]
    assert command[1:3] == ["-m", "ltx_pipelines.a2vid_two_stage"]
    assert command[command.index("--transformer-path") + 1].endswith(AUDIO_FILES[0])
    assert command[command.index("--num-frames") + 1] == "145"
    assert "--audio-max-duration" not in command
    assert command[command.index("--num-inference-steps") + 1] == "30"
    assert command[command.index("--distilled-lora") + 1].endswith(AUDIO_FILES[1])
    assert command[command.index("--distilled-lora") + 2] == "1.0"
    audio_path = Path(command[command.index("--audio-path") + 1])
    assert audio_path.name == "audio.wav"
    assert not audio_path.exists()
    assert result.mp4 == b"mp4 with a track"


def test_the_audio_weights_are_fetched_only_for_a_run_that_follows_a_track(tmp_path, monkeypatch):
    """The pair is 50.9 GB. A studio that draws clips must not be made to fetch it, and a
    run that follows a track must not start without it."""
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    monkeypatch.setattr(Ltx25Runner, "_normalize_audio", staticmethod(normalize_to_wav))
    fetched = []

    def downloader(root):
        fetched.append(root)
        audio_weights(root)

    def fake_process(command, **options):
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4 bytes")

    runner = Ltx25Runner("python", model_dir, process_runner=fake_process, model_downloader=downloader)

    runner.run(job())
    assert fetched == []

    runner.run(audio_job())
    assert fetched == [model_dir]


def test_the_progress_wrapper_counts_the_audio_pipeline_s_guided_stage(tmp_path, monkeypatch):
    """Stage 1 of the audio pipeline samples the guided schedule, not the distilled one, so
    the wrapper's total has to come from the step count on the command line."""
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    audio_weights(model_dir)
    monkeypatch.setattr(Ltx25Runner, "_normalize_audio", staticmethod(normalize_to_wav))
    calls = []

    def fake_execute(self, command, progress=None, cancelled=None):
        calls.append((command, Path(command[1]).read_text()))
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4 with progress")

    monkeypatch.setattr(Ltx25Runner, "_execute", fake_execute)

    Ltx25Runner("python", model_dir).run(audio_job(), lambda _step, _total, _phase: None)

    command, wrapper = calls[0]
    assert command[2] == "ltx_pipelines.a2vid_two_stage"
    assert 'pipeline_name == "ltx_pipelines.a2vid_two_stage"' in wrapper
    assert "STAGE_2_DISTILLED_SIGMA_VALUES" in wrapper


def test_a_track_the_engine_cannot_decode_is_named_before_the_render(tmp_path, monkeypatch):
    """The audio VAE wants stereo PCM, so every track is decoded first. A file the engine
    cannot read has to fail here, not after the transformer has loaded."""

    def refuse(*_args, **_options):
        raise subprocess.CalledProcessError(1, "python")

    monkeypatch.setattr(subprocess, "run", refuse)

    with pytest.raises(StudioError, match="could not be decoded"):
        Ltx25Runner._normalize_audio("python", tmp_path / "in", tmp_path / "out", 5.0)


def test_a_track_that_takes_too_long_to_decode_is_refused(tmp_path, monkeypatch):
    def hang(*_args, **_options):
        raise subprocess.TimeoutExpired("python", 1)

    monkeypatch.setattr(subprocess, "run", hang)

    with pytest.raises(StudioError, match="two minutes"):
        Ltx25Runner._normalize_audio("python", tmp_path / "in", tmp_path / "out", 5.0)


def test_a_decoder_that_cannot_start_names_the_engine_python(tmp_path, monkeypatch):
    def missing(*_args, **_options):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(StudioError, match="executable could not start"):
        Ltx25Runner._normalize_audio("python", tmp_path / "in", tmp_path / "out", 5.0)


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
    # The wrapper is handed the pipeline's module name first, so one script drives either the
    # pipeline that draws a clip and the one that changes a clip.
    assert command[2] == "ltx_pipelines.distilled"
    assert command[3:5] == ["--transformer-path", str(model_dir / FILES[0])]
    assert "samplers.tqdm = report_steps" in wrapper
    # The wrapper reports the whole render as one count, so the page has one
    # percentage to show. It reads both schedules from the pipeline, and the
    # total is their sum, which is only true while each stage samples once.
    assert "from ltx_pipelines.utils.constants import DISTILLED_SIGMA_VALUES" in wrapper
    assert "stage_steps = (len(DISTILLED_SIGMA_VALUES) - 1" in wrapper
    assert "total_steps = sum(stage_steps)" in wrapper
    assert "done_before = sum(stage_steps[:stage])" in wrapper
    assert 'f"STUDIO_STEP 1 {done_before + step} {total_steps}"' in wrapper
    # The sampler breaks on the terminal sigma, so a report after the yield
    # never fires for a stage's last step. The report must come before it.
    report = wrapper.index('f"STUDIO_STEP 1 {done_before + step} {total_steps}"')
    assert report < wrapper.index("        yield value"), "the report must precede the yield"
    # The clip's two denoise passes share one built transformer, and the pass that
    # ends frees it, so the decode behind it starts without it.
    assert "blocks.DiffusionStage._transformer_ctx = holding" in wrapper
    assert 'held["model"] = held["context"].__enter__()' in wrapper
    assert "if this_pass >= 2:" in wrapper
    assert received_callback is callback
    assert reports == []
    assert result.mp4 == b"mp4 with progress"


def _fake_ltx_modules(stage_class, denoise_chunks):
    """The ltx modules the wrapper imports, so the injected code can run with no pipeline."""

    def build(name, **attributes):
        module = types.ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        return module

    distilled = build("ltx_pipelines.distilled", denoise_chunks=denoise_chunks, main=lambda: None)
    blocks = build("ltx_pipelines.utils.blocks", DiffusionStage=stage_class)
    samplers = build("ltx_pipelines.utils.samplers", tqdm=None)
    constants = build(
        "ltx_pipelines.utils.constants",
        DISTILLED_SIGMA_VALUES=(0.0, 1.0, 2.0),
        STAGE_2_DISTILLED_SIGMA_VALUES=(0.0, 1.0),
    )
    utils = build("ltx_pipelines.utils", blocks=blocks, samplers=samplers, constants=constants)
    package = build("ltx_pipelines", distilled=distilled, utils=utils)
    return {
        "ltx_pipelines": package,
        "ltx_pipelines.distilled": distilled,
        "ltx_pipelines.utils": utils,
        "ltx_pipelines.utils.blocks": blocks,
        "ltx_pipelines.utils.samplers": samplers,
        "ltx_pipelines.utils.constants": constants,
    }


def test_the_injected_wrapper_builds_the_transformer_once_and_frees_it_after_the_last_pass(monkeypatch):
    """The wrapper is code the child runs, so run it. Against a fake pipeline it must build
    the transformer on the first denoise pass, hand the same model to the second, and free
    it when the last pass ends, so the decode behind it starts with that room free."""
    built = []
    served = []

    class FakeContext:
        def __enter__(self):
            built.append("build")
            return f"transformer-{len(built)}"

        def __exit__(self, *_error):
            built.append("free")
            return False

    class FakeStage:
        _is_streaming = False

        def _transformer_ctx(self, **_kwargs):
            return FakeContext()

        def denoise(self):
            with self._transformer_ctx() as transformer:
                served.append(transformer)

    def denoise_chunks(stage, chunks=1):
        def produce():
            for _ in range(chunks):
                stage.denoise()
                yield "chunk"

        return produce()

    for name, module in _fake_ltx_modules(FakeStage, denoise_chunks).items():
        monkeypatch.setitem(sys.modules, name, module)

    monkeypatch.setattr(sys, "argv", ["ltx25_progress.py", "ltx_pipelines.distilled"])
    exec(compile(PROGRESS_WRAPPER, "ltx25_progress.py", "exec"), {"__name__": "__main__"})

    passes = sys.modules["ltx_pipelines.distilled"].denoise_chunks
    stage = FakeStage()
    assert built == [], "nothing builds before a pass runs"
    assert list(passes(stage)) == ["chunk"]
    assert built == ["build"], "the first pass builds the transformer once"
    assert list(passes(stage, chunks=2)) == ["chunk", "chunk"]
    assert built == ["build", "free"], "the second pass reuses the first build, then frees it"
    assert served == ["transformer-1", "transformer-1", "transformer-1"]
    # One slot: a second stage frees the first model rather than stacking on it, because
    # two transformers of this size do not fit in the machine's memory together.
    assert list(passes(FakeStage())) == ["chunk"]
    assert built == ["build", "free", "build", "free"]


def test_the_wrapper_leaves_a_streaming_stage_alone(monkeypatch):
    """The block streaming path builds its blocks per pass and tears the stream down with
    them, so a held model would fight it. The wrapper must take the stage's own context."""
    built = []

    class StreamingStage:
        _is_streaming = True

        def _transformer_ctx(self, **_kwargs):
            built.append("build")
            return contextlib.nullcontext("streamed")

    def denoise_chunks(stage, chunks=1):
        def produce():
            for _ in range(chunks):
                with stage._transformer_ctx() as model:
                    assert model == "streamed"
                yield "chunk"

        return produce()

    for name, module in _fake_ltx_modules(StreamingStage, denoise_chunks).items():
        monkeypatch.setitem(sys.modules, name, module)

    monkeypatch.setattr(sys, "argv", ["ltx25_progress.py", "ltx_pipelines.distilled"])
    exec(compile(PROGRESS_WRAPPER, "ltx25_progress.py", "exec"), {"__name__": "__main__"})

    passes = sys.modules["ltx_pipelines.distilled"].denoise_chunks
    assert list(passes(StreamingStage())) == ["chunk"]
    assert list(passes(StreamingStage())) == ["chunk"]
    assert built == ["build", "build"], "a streamed stage is never held"


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


def test_runner_reports_a_streamed_pipeline_failure_with_what_the_pipeline_said():
    """A run that dies of memory says so on its own last line, and the runner reads the
    child's output for step markers and drops the rest: this tail is the only account of the
    failure a person can act on."""
    command = [
        sys.executable,
        "-c",
        "import sys; print('RuntimeError: MPS backend out of memory', file=sys.stderr); raise SystemExit(2)",
    ]

    with pytest.raises(StudioError, match="pipeline failed with exit status 2") as failure:
        Ltx25Runner("python", ".")._execute(command, lambda _step, _total, _phase: None)

    assert "MPS backend out of memory" in str(failure.value)


def test_runner_says_so_when_a_dying_pipeline_says_nothing():
    command = [sys.executable, "-c", "raise SystemExit(3)"]

    with pytest.raises(StudioError, match="failed with exit status 3 and said nothing"):
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


def edit_job(clip=b"clip bytes", strength=0.8):
    return VideoJob(
        "A night version of the same place",
        768,
        448,
        97,
        24,
        7,
        edit=VideoEdit(
            adapter="relight",
            strength=strength,
            lora_file="relight.safetensors",
            clip=clip,
            clip_name="input.mp4",
            stage_2_conditioning=True,
        ),
    )


def test_an_edit_run_drives_the_in_context_pipeline_with_the_clip_and_the_adapter(tmp_path, monkeypatch):
    """An edit is a different pipeline, not a different model: the same six files, the
    adapter as a LoRA, and the clip written down and named as the conditioning input. The
    flag that keeps stage 2 conditioned rides along, because without it the second stage
    runs the bare checkpoint and redraws the scene."""
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()
    (lora_dir / "relight.safetensors").write_bytes(b"adapter weights")
    calls = []

    def fake_execute(self, command, progress=None, cancelled=None):
        calls.append((command, Path(command[command.index("--video-conditioning") + 1]).read_bytes()))
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4 with an edit")

    monkeypatch.setattr(Ltx25Runner, "_execute", fake_execute)
    result = Ltx25Runner("python", model_dir, lora_dir=lora_dir).run(edit_job(), lambda step, total, phase: None)

    command, clip = calls[0]
    # The wrapper is the entry point when a run reports progress, and it is handed the
    # pipeline's module name so one script can drive either pipeline.
    assert command[1].endswith("ltx25_progress.py")
    assert command[2] == "ltx_pipelines.ic_lora"
    assert command[command.index("--lora") + 1 : command.index("--lora") + 3] == [
        str(lora_dir / "relight.safetensors"),
        "0.8",
    ]
    assert command[command.index("--video-conditioning") + 2] == "1.0"
    assert "--stage-2-ic-lora" in command
    assert clip == b"clip bytes"
    assert result.mp4 == b"mp4 with an edit"


def test_an_edit_without_progress_still_names_the_in_context_pipeline(tmp_path, monkeypatch):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()
    (lora_dir / "relight.safetensors").write_bytes(b"adapter weights")
    seen = []

    def fake_process_runner(command, **_options):
        seen.append(command)
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4")

    runner = Ltx25Runner("python", model_dir, process_runner=fake_process_runner, lora_dir=lora_dir)
    runner.run(edit_job(strength=1.0))

    assert seen[0][2] == "ltx_pipelines.ic_lora"
    assert seen[0][seen[0].index("--lora") + 2] == "1.0"


def test_an_edit_with_no_adapter_directory_configured_says_so(tmp_path, monkeypatch):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)

    def fake_execute(self, command, progress=None, cancelled=None):
        pytest.fail("a run with no adapter directory reached the pipeline")

    monkeypatch.setattr(Ltx25Runner, "_execute", fake_execute)

    with pytest.raises(StudioError, match="lora_dir"):
        Ltx25Runner("python", model_dir).run(edit_job(), lambda step, total, phase: None)


def test_an_edit_whose_adapter_is_not_downloaded_says_where_it_goes(tmp_path, monkeypatch):
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()

    with pytest.raises(StudioError, match="not on disk"):
        Ltx25Runner("python", model_dir, lora_dir=lora_dir).run(edit_job(), lambda step, total, phase: None)


def test_an_edit_whose_adapter_measured_better_without_it_leaves_stage_two_bare(tmp_path, monkeypatch):
    """The flag is the adapter's fact, not a constant: an adapter measured without it must not
    get it, or the run does something nobody measured."""
    model_dir = tmp_path / "ltx-models"
    model_dir.mkdir()
    weights(model_dir)
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()
    (lora_dir / "relight.safetensors").write_bytes(b"adapter weights")
    calls = []

    def fake_execute(self, command, progress=None, cancelled=None):
        calls.append(command)
        Path(command[command.index("--output-path") + 1]).write_bytes(b"mp4")

    monkeypatch.setattr(Ltx25Runner, "_execute", fake_execute)
    job = edit_job()
    bare = VideoJob(
        job.prompt,
        job.width,
        job.height,
        job.num_frames,
        job.frame_rate,
        job.seed,
        edit=VideoEdit(
            adapter="relight",
            strength=1.0,
            lora_file="relight.safetensors",
            clip=b"clip bytes",
            clip_name="input.mp4",
        ),
    )

    Ltx25Runner("python", model_dir, lora_dir=lora_dir).run(bare, lambda step, total, phase: None)

    assert "--stage-2-ic-lora" not in calls[0]
