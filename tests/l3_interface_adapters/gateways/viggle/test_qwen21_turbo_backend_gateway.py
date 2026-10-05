"""The Viggle Turbo gateway: which model runs, and which schedule it runs on.

The two models are handed in rather than built here, so these tests hand in
recorders. The one behaviour worth proving is the schedule: mflux's edit call
takes no scheduler, so the gateway supplies it, and the generate half gets it
through an argument instead.
"""

from contextlib import contextmanager

import pytest

from studio.l1_entities.errors import StudioError
from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.viggle import qwen21_turbo_backend_gateway as module
from studio.l3_interface_adapters.gateways.viggle.qwen21_turbo_backend_gateway import (
    Qwen21TurboBackendGateway,
)


def job(mode="generate"):
    return ImageJob(mode=mode, prompt="a pear", seed=5, options={"steps": 6}, references=())


class Engine:
    """A model stand-in, recording what was asked of it."""

    def __init__(self, name, events, patched):
        self.name = name
        self.events = events
        self.patched = patched

    def load(self):
        self.events.append(("load", self.name))

    def release(self):
        self.events.append(("release", self.name))

    def run(self, job, on_step, should_stop):
        self.events.append(("run", self.name, self.patched[0]))
        return f"{self.name} made {job.mode}"


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """A gateway over two recorders, and a flag that says whether the patch is on."""
    events = []
    patched = [False]

    @contextmanager
    def recording_schedule():
        patched[0] = True
        try:
            yield
        finally:
            patched[0] = False

    monkeypatch.setattr(module, "viggle_schedule", recording_schedule)
    adapter = tmp_path / "turbo.safetensors"
    adapter.write_bytes(b"weights")
    gateway = Qwen21TurboBackendGateway(
        Engine("generate", events, patched), Engine("edit", events, patched), badge="bf16", lora_path=str(adapter)
    )
    return gateway, events, patched


def test_a_backend_without_its_adapter_says_where_to_get_it(tmp_path):
    """A backend is built whether or not it is used, so this cannot refuse at build
    time: the stub builds every backend. It refuses when the model is asked for, and
    the message carries the whole command rather than a path."""
    gateway = Qwen21TurboBackendGateway(
        Engine("generate", [], [False]),
        Engine("edit", [], [False]),
        badge="bf16",
        lora_path=str(tmp_path / "missing.safetensors"),
    )
    with pytest.raises(StudioError, match="Viggle Turbo needs its adapter"):
        gateway.load()
    with pytest.raises(StudioError, match="hf download"):
        gateway.load()


def test_the_recipe_names_the_command_that_works():
    """huggingface_hub 2.x deprecated `huggingface-cli`, and it now exits without
    downloading anything. Measured 2026-10-05: the first real fetch of this adapter
    failed on exactly that, so the message a user gets has to name `hf`."""
    assert "hf download" in module.RECIPE
    assert "huggingface-cli" not in module.RECIPE


def test_a_backend_with_its_adapter_loads_the_generate_model(wired):
    gateway, events, _ = wired
    gateway.load()
    assert events == [("load", "generate")]


def test_generate_frees_the_edit_model_and_runs_without_the_patch(wired):
    """Generate is told which schedule to use, so it needs no patch around it."""
    gateway, events, patched = wired
    assert gateway.run(job("generate"), None, None) == "generate made generate"
    assert events == [("release", "edit"), ("run", "generate", False)]
    assert patched[0] is False


def test_edit_frees_the_generate_model_and_runs_inside_the_patch(wired):
    """mflux's edit call cannot be told which scheduler to use, so the gateway puts
    the turbo schedule in force for the length of that call and no longer."""
    gateway, events, patched = wired
    assert gateway.run(job("edit"), None, None) == "edit made edit"
    assert events == [("release", "generate"), ("run", "edit", True)]
    assert patched[0] is False  # and off again once the call returns


def test_release_frees_both_models(wired):
    gateway, events, _ = wired
    gateway.release()
    assert events == [("release", "generate"), ("release", "edit")]


def test_the_gateway_reports_the_backends_capabilities(wired):
    gateway, _, _ = wired
    assert gateway.capabilities().backend_id == "viggle_turbo"
