"""The diffusers edit child: its flags, its stdio contract, and the pipeline under them.

The child runs in its own environment, on diffusers and torch. diffusers is not
installed here, so every test that builds a pipeline stubs it through
`heavy_modules` and asserts the arguments the child passed to it. The weights
are never read.
"""

import base64
import importlib.util
import io
import json
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import torch
from PIL import Image

from tests.support import SOURCE_ROOT
from tests.support.heavy import heavy_modules
from tests.support.images import png

EDIT_SCRIPT = SOURCE_ROOT / "l3_interface_adapters/gateways/qwen21/qwen21_edit.py"


def load_edit_child():
    """The edit child as a module, so its stdio contract can be driven in-process."""
    spec = importlib.util.spec_from_file_location("qwen21_edit_under_test", EDIT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def child_job(**overrides):
    return {
        "prompt": "make it cobalt",
        "images": [base64.b64encode(png(8, 8).png).decode("ascii")],
        "steps": 2,
        **overrides,
    }


def job_lines(*jobs):
    return [json.dumps(job) for job in jobs]


def drive_child(monkeypatch, edit, lines):
    """Feed the child's stdio loop the given lines, and return its answers and its stderr."""
    stdin = io.BytesIO("".join(line + "\n" for line in lines).encode())
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=stdin))
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    edit.run_stdio(SimpleNamespace(offload=False, vae_encode_on_mps=False))
    answers = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    return answers, stderr.getvalue()


def no_weights(offload, encode_on_mps):
    raise RuntimeError("no weights for Qwen/Qwen-Image-2.1")


class FakeImage:
    def __init__(self):
        self.moved = None

    def to(self, device, dtype):
        self.moved = (device, dtype)
        return self


class FakeVae:
    """The VAE of a pipeline stand-in: it records every device and dtype it is moved to."""

    def __init__(self):
        self.device, self.dtype = "mps", torch.bfloat16
        self.moves = []

    def to(self, device, dtype=None):
        self.moves.append((device, dtype))
        self.device = device
        self.dtype = dtype or self.dtype


class FakeLatents:
    def __init__(self):
        self.moves = []

    def to(self, device, dtype):
        self.moves.append((device, dtype))
        return self


class FakePipeline:
    """A QwenImage21Pipeline stand-in with the two methods the child calls on it."""

    def __init__(self, explode: bool = False):
        self.vae = FakeVae()
        self.calls = []
        self.explode = explode

    def _encode_vae_image(self, image, generator):
        if self.explode:
            raise RuntimeError("the encode died")
        self.calls.append("pipeline encode")
        return FakeLatents()

    def to(self, device):
        self.calls.append(("to", device))

    def enable_model_cpu_offload(self, device):
        self.calls.append(("offload", device))


class FakeEditPipeline:
    """A pipeline stand-in that answers one job and reports each step like diffusers."""

    def __init__(self, fail_first=False):
        self.fail_first = fail_first
        self.jobs = []
        self.images = [Image.new("RGB", (32, 24), "red")]

    def __call__(self, **kwargs):
        self.jobs.append(kwargs)
        if self.fail_first and len(self.jobs) == 1:
            raise RuntimeError("the reference image is too small")
        callback = kwargs["callback_on_step_end"]  # None when no run asked for progress
        for index in range(kwargs["num_inference_steps"]):
            if callback is not None:
                callback(None, index, None, None)
        return SimpleNamespace(images=self.images)


def stdio_job(**overrides):
    return {
        "prompt": "make it night",
        "images": ["a reference"],
        "negative_prompt": None,
        "true_cfg_scale": 1.0,
        "steps": 4,
        "output_resolution": 1024,
        "use_kv_cache": True,
        "seed": 7,
        **overrides,
    }


def diffusers_stub(pipeline_class):
    return {"diffusers": {"QwenImage21Pipeline": pipeline_class}}


def test_the_flag_interface_reads_every_switch(monkeypatch):
    edit = load_edit_child()
    argv = [
        "qwen21_edit.py", "--prompt", "make it night", "--image", "a.png", "--image", "b.png",
        "--steps", "12", "--negative-prompt", "blur", "--true-cfg-scale", "2.5", "--seed", "3",
        "--output-resolution", "768", "--output", "night.png", "--offload", "--vae-encode-on-mps", "--no-kv-cache",
    ]  # fmt: skip
    monkeypatch.setattr(sys, "argv", argv)
    args = edit.parse_args()
    assert args.prompt == "make it night" and args.image == ["a.png", "b.png"]
    assert (args.steps, args.seed, args.output_resolution, args.output) == (12, 3, 768, "night.png")
    assert (args.negative_prompt, args.true_cfg_scale) == ("blur", 2.5)
    assert args.offload and args.vae_encode_on_mps and args.no_kv_cache and not args.stdio


def test_the_stdio_switch_needs_no_prompt_and_no_image(monkeypatch):
    edit = load_edit_child()
    monkeypatch.setattr(sys, "argv", ["qwen21_edit.py", "--stdio"])
    args = edit.parse_args()
    assert args.stdio and args.image is None and args.prompt is None
    assert (args.steps, args.output_resolution, args.output) == (40, 1024, "qwen21_edit.png")
    assert (args.seed, args.negative_prompt, args.true_cfg_scale) == (None, None, 1.0)
    assert not args.offload and not args.vae_encode_on_mps and not args.no_kv_cache


def test_a_run_without_a_prompt_or_an_image_is_refused(monkeypatch, capsys):
    edit = load_edit_child()
    monkeypatch.setattr(sys, "argv", ["qwen21_edit.py", "--prompt", "make it night"])
    with pytest.raises(SystemExit) as exit_info:
        edit.parse_args()
    assert exit_info.value.code == 2
    assert "--prompt and --image are required unless --stdio is given" in capsys.readouterr().err


def test_load_references_reads_every_image_as_rgba(tmp_path):
    """RGBA, because the input's own alpha reaches the VAE and an edit can return alpha."""
    edit = load_edit_child()
    first, second = tmp_path / "a.png", tmp_path / "b.png"
    Image.new("RGB", (32, 48), "red").save(first)
    Image.new("RGB", (16, 16), "blue").save(second)
    images = edit.load_references([str(first), str(second)])
    assert [image.size for image in images] == [(32, 48), (16, 16)]
    assert all(image.mode == "RGBA" for image in images)


def test_a_reference_past_the_limit_is_refused_before_anything_loads(tmp_path):
    edit = load_edit_child()
    paths = [str(tmp_path / f"{index}.png") for index in range(11)]
    with pytest.raises(SystemExit, match="11 references given, the model takes at most 10"):
        edit.load_references(paths)


def test_a_missing_reference_is_named(tmp_path):
    """A bad path fails before the model loads, not after 30 seconds of loading."""
    edit = load_edit_child()
    with pytest.raises(SystemExit, match="reference image not found"):
        edit.load_references([str(tmp_path / "gone.png")])


def header_args(**overrides):
    settings = {
        "image": ["room.png"],
        "prompt": "make it night",
        "steps": 40,
        "true_cfg_scale": 1.0,
        "no_kv_cache": False,
        "vae_encode_on_mps": False,
        "output_resolution": 1024,
        "seed": None,
        "output": "night.png",
        **overrides,
    }
    return SimpleNamespace(**settings)


def pipeline_builder(pipeline):
    """A QwenImage21Pipeline stand-in whose from_pretrained hands back the given pipeline."""
    builder = Mock()
    builder.from_pretrained.return_value = pipeline
    return builder


def test_the_header_lays_out_the_settings_this_run_will_use(capsys):
    edit = load_edit_child()
    edit.print_header(header_args(), [Image.new("RGBA", (32, 48))])
    printed = capsys.readouterr().out
    assert "room.png (32x48)" in printed
    assert "40 steps, true CFG 1.0" in printed
    assert "VAE encode  : cpu fp32" in printed
    assert "KV cache    : on" in printed
    assert "Seed        : random" in printed


def test_the_header_names_the_two_diagnostic_switches(capsys):
    edit = load_edit_child()
    args = header_args(no_kv_cache=True, vae_encode_on_mps=True, seed=7)
    edit.print_header(args, [Image.new("RGBA", (32, 48))])
    printed = capsys.readouterr().out
    assert "VAE encode  : mps (known broken)" in printed
    assert "KV cache    : off" in printed
    assert "Seed        : 7" in printed


def test_the_vae_encode_runs_on_the_cpu_in_fp32_and_the_vae_goes_back():
    """The MPS backend miscomputes this VAE encoder: contrast falls from 64.2 to 17.8 at
    both bf16 and fp32, while CPU fp32 reproduces the source. So the encode moves to the
    CPU and the denoise steps stay on MPS, at about 16s per run."""
    edit = load_edit_child()
    pipe = FakePipeline()
    edit._encode_vae_on_cpu(pipe)
    latents = pipe._encode_vae_image(FakeImage(), "the generator")

    assert pipe.vae.moves == [("cpu", torch.float32), ("mps", torch.bfloat16)]
    assert pipe.calls[0] == "pipeline encode"
    assert latents.moves == [("mps", torch.bfloat16)]


def test_the_vae_goes_back_even_when_the_encode_fails():
    """The restore sits in a finally, so a failed encode leaves no fp32 VAE behind."""
    edit = load_edit_child()
    pipe = FakePipeline(explode=True)
    edit._encode_vae_on_cpu(pipe)
    with pytest.raises(RuntimeError, match="the encode died"):
        pipe._encode_vae_image(FakeImage(), "the generator")
    assert pipe.vae.moves == [("cpu", torch.float32), ("mps", torch.bfloat16)]


def test_a_machine_without_mps_is_refused(monkeypatch):
    edit = load_edit_child()
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    with heavy_modules(diffusers_stub(Mock())), pytest.raises(SystemExit, match="no MPS device"):
        edit.build_pipeline(offload=False, encode_on_mps=False)


def test_the_pipeline_is_built_in_bf16_and_moved_to_mps(monkeypatch):
    edit = load_edit_child()
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
    pipeline = FakePipeline()
    builder = pipeline_builder(pipeline)
    with heavy_modules(diffusers_stub(builder)):
        built = edit.build_pipeline(offload=False, encode_on_mps=False)

    assert built is pipeline
    assert builder.from_pretrained.call_args.args == ("Qwen/Qwen-Image-2.1",)
    assert builder.from_pretrained.call_args.kwargs == {"torch_dtype": torch.bfloat16}
    assert pipeline.calls == [("to", "mps")]
    pipeline._encode_vae_image(FakeImage(), "the generator")  # the default encode is the CPU one
    assert pipeline.vae.moves == [("cpu", torch.float32), ("mps", torch.bfloat16)]


def test_an_offload_run_keeps_the_components_on_the_cpu_when_they_are_idle(monkeypatch):
    edit = load_edit_child()
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
    pipeline = FakePipeline()
    with heavy_modules(diffusers_stub(pipeline_builder(pipeline))):
        edit.build_pipeline(offload=True, encode_on_mps=False)
    assert pipeline.calls == [("offload", "mps")]


def test_the_mps_encode_is_kept_when_it_is_asked_for(monkeypatch):
    """Diagnostic only: the flag exists to reproduce the device bug on demand."""
    edit = load_edit_child()
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
    pipeline = FakePipeline()
    with heavy_modules(diffusers_stub(pipeline_builder(pipeline))):
        built = edit.build_pipeline(offload=False, encode_on_mps=True)
    built._encode_vae_image(FakeImage(), "the generator")
    assert pipeline.calls == [("to", "mps"), "pipeline encode"]
    assert pipeline.vae.moves == []


def test_a_run_gives_the_pipeline_the_job_and_reports_the_cost(monkeypatch):
    edit = load_edit_child()
    monkeypatch.setattr(torch.mps, "driver_allocated_memory", lambda: 2 * 1024**3)
    pipe = FakeEditPipeline()
    said = []
    image, seed, elapsed = edit.run_edit(pipe, stdio_job(), said.append, None)

    assert pipe.jobs[0]["prompt"] == "make it night" and pipe.jobs[0]["image"] == ["a reference"]
    assert pipe.jobs[0]["num_inference_steps"] == 4 and pipe.jobs[0]["output_resolution"] == 1024
    assert pipe.jobs[0]["use_kv_cache"] is True and pipe.jobs[0]["negative_prompt"] is None
    assert pipe.jobs[0]["callback_on_step_end"] is None  # no progress was asked for
    assert pipe.jobs[0]["generator"].initial_seed() == 7  # a CPU generator keeps the seed honest
    assert image is pipe.images[0] and seed == 7 and elapsed >= 0
    assert said[1] == "MPS memory  : 2.0 GiB allocated at exit"
    assert said[0].startswith("Timing      : ") and said[0].endswith("s total")


def test_a_run_reports_progress_through_the_pipeline_callback(monkeypatch):
    """The child prints "step N/M" on stderr, which is all the page sees while it waits."""
    edit = load_edit_child()
    monkeypatch.setattr(torch.mps, "driver_allocated_memory", lambda: 0)
    pipe = FakeEditPipeline()
    steps = []
    edit.run_edit(pipe, stdio_job(), lambda line: None, lambda step, total: steps.append((step, total)))

    assert steps == [(1, 4), (2, 4), (3, 4), (4, 4)]  # diffusers counts from 0, the page from 1
    callback = pipe.jobs[0]["callback_on_step_end"]
    assert callback(None, 4, None, "the tensors") == "the tensors"  # diffusers takes the tensors back


def test_a_run_without_a_seed_picks_one_and_reports_the_one_it_used(monkeypatch):
    edit = load_edit_child()
    monkeypatch.setattr(torch.mps, "driver_allocated_memory", lambda: 0)
    monkeypatch.setattr(edit, "random", SimpleNamespace(randint=Mock(return_value=1234)))
    pipe = FakeEditPipeline()
    _, seed, _ = edit.run_edit(pipe, stdio_job(seed=None), lambda line: None, None)
    assert edit.random.randint.call_args.args == (0, 1_000_000_000)
    assert seed == 1234 and pipe.jobs[0]["generator"].initial_seed() == 1234


def test_job_from_args_carries_what_the_pipeline_reads():
    edit = load_edit_child()
    args = SimpleNamespace(
        prompt="make it night", negative_prompt=None, true_cfg_scale=1.0, steps=40, output_resolution=1024,
        no_kv_cache=True, seed=7,
    )  # fmt: skip
    images = [Image.new("RGBA", (8, 8))]
    assert edit.job_from_args(args, images) == {
        "prompt": "make it night",
        "images": images,
        "negative_prompt": None,
        "true_cfg_scale": 1.0,
        "steps": 40,
        "output_resolution": 1024,
        "use_kv_cache": False,
        "seed": 7,
    }


def test_a_stdio_job_fills_in_the_defaults_the_page_leaves_out():
    edit = load_edit_child()
    job = edit.parse_stdio_job({"prompt": "make it night", "images": [base64.b64encode(png(8, 8).png).decode()]})
    assert job["images"][0].size == (8, 8) and job["images"][0].mode == "RGBA"
    assert (job["negative_prompt"], job["true_cfg_scale"], job["steps"]) == (None, 1.0, 40)
    assert (job["output_resolution"], job["use_kv_cache"], job["seed"]) == (1024, True, None)


def test_a_stdio_job_carries_the_values_the_server_sent():
    edit = load_edit_child()
    request = {
        "prompt": "make it night",
        "images": [base64.b64encode(png(8, 8).png).decode()],
        "negative_prompt": "blur",
        "true_cfg_scale": 2.5,
        "steps": "12",
        "output_resolution": "768",
        "use_kv_cache": False,
        "seed": 3,
    }
    job = edit.parse_stdio_job(request)
    assert (job["negative_prompt"], job["true_cfg_scale"]) == ("blur", 2.5)
    assert (job["steps"], job["output_resolution"], job["use_kv_cache"], job["seed"]) == (12, 768, False, 3)


def test_a_stdio_job_without_a_reference_is_refused():
    edit = load_edit_child()
    with pytest.raises(ValueError, match="the job carried no reference image"):
        edit.parse_stdio_job({"prompt": "make it night"})


def test_a_stdio_job_past_the_reference_limit_is_refused():
    edit = load_edit_child()
    encoded = [base64.b64encode(png(8, 8).png).decode()] * 11
    with pytest.raises(ValueError, match="11 references given, the model takes at most 10"):
        edit.parse_stdio_job({"prompt": "make it night", "images": encoded})


def test_an_error_answers_where_the_caller_waits_for_it(capsys):
    edit = load_edit_child()
    edit.answer_error(ValueError("the job carried no reference image"))
    assert capsys.readouterr().out == '{"error": "ValueError: the job carried no reference image"}\n'


def test_a_failed_pipeline_build_answers_with_the_error(monkeypatch):
    """The build sits inside the job's error contract, so the reason reaches the caller."""
    edit = load_edit_child()
    monkeypatch.setattr(edit, "build_pipeline", no_weights)
    answers, _ = drive_child(monkeypatch, edit, job_lines(child_job()))
    assert answers == [{"error": "RuntimeError: no weights for Qwen/Qwen-Image-2.1"}]


def test_a_failed_pipeline_build_ends_the_child(monkeypatch):
    """A child with no pipeline has nothing to serve: it answers, then goes."""
    edit = load_edit_child()
    monkeypatch.setattr(edit, "build_pipeline", no_weights)
    answers, _ = drive_child(monkeypatch, edit, job_lines(child_job(), child_job()))
    assert len(answers) == 1 and "error" in answers[0]


def test_a_job_the_child_cannot_parse_is_answered_and_the_loop_goes_on(monkeypatch):
    edit = load_edit_child()
    built = Mock()
    monkeypatch.setattr(edit, "build_pipeline", built)
    answers, _ = drive_child(monkeypatch, edit, ['{"prompt": "make it night"}', "not json at all"])
    assert answers[0] == {"error": "the job carried no reference image"}
    assert answers[1]["error"].startswith("Expecting value")  # what json says about a line that is not JSON
    assert built.call_count == 0  # nothing was built for a job that never reached the pipeline


def test_the_stdio_loop_answers_every_job_over_one_pipeline(monkeypatch):
    """Loading the pipeline costs 20 to 36 seconds, so a caller sending several edits
    pays that once. Progress goes to stderr, one JSON result per job to stdout."""
    edit = load_edit_child()
    pipeline = FakeEditPipeline(fail_first=True)
    built = []

    def build(offload, encode_on_mps):
        built.append(offload)
        return pipeline

    monkeypatch.setattr(edit, "build_pipeline", build)
    monkeypatch.setattr(torch.mps, "driver_allocated_memory", lambda: 0)
    answers, said = drive_child(monkeypatch, edit, [*job_lines(child_job()), "", *job_lines(child_job())])

    assert answers[0] == {"error": "RuntimeError: the reference image is too small"}
    assert (answers[1]["width"], answers[1]["height"]) == (32, 24)
    assert base64.b64decode(answers[1]["image"])[:4] == b"\x89PNG"
    assert isinstance(answers[1]["seed"], int) and isinstance(answers[1]["seconds"], float)
    assert built == [False]  # one build served both jobs
    assert "Loaded" in said and "ready" in said
    assert "step 0/2" in said and "step 2/2" in said


def test_main_runs_one_job_from_the_flags(monkeypatch, tmp_path, capsys):
    edit = load_edit_child()
    output = tmp_path / "night.png"
    args = SimpleNamespace(
        stdio=False, image=["room.png"], prompt="make it night", negative_prompt=None, true_cfg_scale=1.0,
        steps=2, seed=7, output_resolution=1024, output=str(output), offload=False, vae_encode_on_mps=False,
        no_kv_cache=False,
    )  # fmt: skip
    monkeypatch.setattr(edit, "parse_args", lambda: args)
    monkeypatch.setattr(edit, "load_references", lambda paths: [Image.new("RGBA", (8, 8))])
    monkeypatch.setattr(edit, "build_pipeline", lambda offload, encode_on_mps: FakeEditPipeline())
    monkeypatch.setattr(torch.mps, "driver_allocated_memory", lambda: 0)

    edit.main()

    assert output.read_bytes()[:4] == b"\x89PNG"
    printed = capsys.readouterr().out
    assert "room.png (8x8)" in printed and "Loaded" in printed
    assert "Seed used   : 7" in printed


def test_main_hands_the_stdio_switch_to_the_loop(monkeypatch):
    edit = load_edit_child()
    args = SimpleNamespace(stdio=True)
    loop = Mock()
    monkeypatch.setattr(edit, "parse_args", lambda: args)
    monkeypatch.setattr(edit, "run_stdio", loop)
    edit.main()
    assert loop.call_args.args == (args,)


def test_the_script_starts_the_stdio_loop_as_main(monkeypatch):
    """`echo ... | qwen21_edit.py --stdio` is how the server starts the child, so the
    guard has to reach main, and the loop has to end when stdin closes."""
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "argv", [str(EDIT_SCRIPT), "--stdio"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"")))
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    runpy.run_path(str(EDIT_SCRIPT), run_name="__main__")
    assert stdout.getvalue() == ""
