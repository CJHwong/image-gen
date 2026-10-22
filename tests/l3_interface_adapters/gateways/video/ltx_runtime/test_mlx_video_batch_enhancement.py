import argparse
import sys
import weakref
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

from studio.l3_interface_adapters.gateways.video.ltx_runtime import mlx_video_batch_enhancement as child


@pytest.fixture
def engine(monkeypatch):
    events = []
    instances = []
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("-p", dest="prompt")
    parser.add_argument("--seed", type=int, default=-1)
    parser.add_argument("--gemma", default="native-gemma")

    class Images(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            setattr(namespace, self.dest, [SimpleNamespace(path=values)])

    parser.add_argument("--image", dest="images", action=Images, default=None)
    cli = cast(Any, ModuleType("ltx_pipelines_mlx.cli"))
    cli._build_parser = lambda: parser
    cli._guard_enhance_not_gemma4 = lambda path: events.append(("guard", path))
    encoder = cast(Any, ModuleType("ltx_core_mlx.text_encoders.gemma.encoders.base_encoder"))
    memory = cast(Any, ModuleType("ltx_core_mlx.utils.memory"))

    class Model:
        def __init__(self):
            instances.append(weakref.ref(self))

        def load(self, path):
            events.append(("load", path))

        def enhance_t2v(self, prompt, seed):
            events.append(("t2v", prompt, seed))
            return prompt + " enhanced"

        def enhance_i2v(self, prompt, image, seed):
            events.append(("i2v", prompt, image, seed))
            return prompt + " animated"

    encoder.GemmaLanguageModel = Model
    helper = cast(Any, ModuleType("mlx_image_prompt_enhancement"))
    helper.ImagePromptEnhancer = Model
    monkeypatch.setitem(sys.modules, helper.__name__, helper)

    def cleanup():
        events.append(("cleanup",))
        events.append(("alive_at_cleanup", any(instance() is not None for instance in instances)))

    memory.aggressive_cleanup = cleanup
    for name, module in [(cli.__name__, cli), (encoder.__name__, encoder), (memory.__name__, memory)]:
        monkeypatch.setitem(sys.modules, name, module)
    return events, instances, encoder


def test_unique_seeds_and_native_strategies_share_one_load_and_release_before_render(engine, capsys):
    events, instances, _ = engine
    commands = [
        ["cli", "generate", "-p", "cat", "--seed", "7", "--enhance-prompt"],
        ["cli", "generate", "-p", "dog", "--seed", "8", "--image", "ref.png", "--enhance-prompt"],
        ["cli", "a2v", "-p", "song", "--seed", "9", "--enhance-prompt"],
        ["cli", "generate", "-p", "unchanged", "--seed", "10"],
    ]
    child.enhance_commands(commands)
    assert [command[command.index("-p") + 1] for command in commands] == [
        "cat enhanced",
        "dog animated",
        "song enhanced",
        "unchanged",
    ]
    assert all("--enhance-prompt" not in command for command in commands)
    assert len(instances) == 2
    assert events == [
        ("guard", "native-gemma"),
        ("guard", "native-gemma"),
        ("guard", "native-gemma"),
        ("load", "native-gemma"),
        ("t2v", "cat", 7),
        ("t2v", "song", 9),
        ("cleanup",),
        ("alive_at_cleanup", False),
        ("load", "native-gemma"),
        ("i2v", "dog", "ref.png", 8),
        ("cleanup",),
        ("alive_at_cleanup", False),
    ]
    assert "[Enhancing batch prompt 3/3]" in capsys.readouterr().err


@pytest.mark.parametrize("seed", [[], ["--seed", "-1"]])
def test_random_seed_is_resolved_once_for_enhancement_and_video(engine, monkeypatch, seed):
    events, _, _ = engine
    monkeypatch.setattr(child.random, "randint", lambda first, last: 123)
    command = ["cli", "generate", "-p", "cat", *seed, "--enhance-prompt"]
    child.enhance_commands([command])
    assert command.count("--seed") == 1
    assert command[command.index("--seed") + 1] == "123"
    assert ("t2v", "cat", 123) in events


def test_no_enhancement_never_imports_or_loads_an_engine(monkeypatch):
    def unexpected(*args):
        raise AssertionError("engine imported")

    monkeypatch.setattr(child.importlib, "import_module", unexpected)
    commands = [["cli", "generate", "-p", "cat"]]
    child.enhance_commands(commands)
    assert commands == [["cli", "generate", "-p", "cat"]]


@pytest.mark.parametrize("where", ["load", "enhance_t2v"])
def test_failure_releases_model_and_cleans_before_propagating(engine, monkeypatch, where):
    events, _, encoder = engine

    def failure(*args, **kwargs):
        raise RuntimeError("enhancement failed")

    monkeypatch.setattr(encoder.GemmaLanguageModel, where, failure)
    with pytest.raises(RuntimeError, match="enhancement failed"):
        child.enhance_commands([["cli", "generate", "-p", "cat", "--enhance-prompt"]])
    assert ("cleanup",) in events


@pytest.mark.parametrize("policy", ["offload", "sequential"])
@pytest.mark.parametrize("entrypoint", [False, True])
def test_child_enhances_every_prompt_before_encoding_or_rendering(engine, monkeypatch, tmp_path, policy, entrypoint):
    import json

    from studio.l3_interface_adapters.gateways.video.ltx_runtime import mlx_video_batch_child as batch

    events, instances, _ = engine
    monkeypatch.setitem(sys.modules, "mlx_video_batch_enhancement", child)
    cli = cast(Any, sys.modules["ltx_pipelines_mlx.cli"])

    def render():
        assert instances[0]() is None
        assert "--enhance-prompt" not in sys.argv
        events.append(("render", sys.argv[sys.argv.index("-p") + 1]))

    def retain(commands, policy):
        assert instances[0]() is None
        assert events[-1] == ("alive_at_cleanup", False)
        events.append(("retain", [command[command.index("-p") + 1] for command in commands]))

    cli.main = render
    monkeypatch.setattr(batch, "retain_pipeline", retain)
    commands = [["cli", "generate", "-p", prompt, "--seed", "7", "--enhance-prompt"] for prompt in ["cat", "dog"]]
    manifest = tmp_path / "commands.json"
    manifest.write_text(json.dumps(commands))
    for index in [1, 2]:
        (tmp_path / f"{index}.ack").touch()
    monkeypatch.setattr(sys, "argv", ["enhancer", str(manifest)])
    if entrypoint:
        import runpy

        runpy.run_path(child.__file__, run_name="__main__")
    else:
        child.main()
    batch.execute(manifest, policy)
    assert [event for event in events if event[0] == "render"] == [
        ("render", "cat enhanced"),
        ("render", "dog enhanced"),
    ]
    assert events.index(("t2v", "dog", 7)) < events.index(("render", "cat enhanced"))
    assert sum(event[0] == "load" for event in events) == 1
    assert sum(event[0] == "retain" for event in events) == (policy != "sequential")


@pytest.mark.parametrize("second_checkpoint", ["native-gemma", "other-gemma"])
def test_image_groups_reuse_each_checkpoint_without_reordering_results(engine, second_checkpoint):
    events, instances, _ = engine
    commands = [
        ["cli", "generate", "-p", "first", "--seed", "7", "--image", "first.png", "--enhance-prompt"],
        [
            "cli",
            "generate",
            "-p",
            "second",
            "--seed",
            "8",
            "--image",
            "second.png",
            "--gemma",
            second_checkpoint,
            "--enhance-prompt",
        ],
    ]
    child.enhance_commands(commands)
    assert len(instances) == (1 if second_checkpoint == "native-gemma" else 2)
    assert [command[command.index("-p") + 1] for command in commands] == ["first animated", "second animated"]
    assert [(event[2], event[3]) for event in events if event[0] == "i2v"] == [("first.png", 7), ("second.png", 8)]
    assert all(event == ("alive_at_cleanup", False) for event in events if event[0] == "alive_at_cleanup")
