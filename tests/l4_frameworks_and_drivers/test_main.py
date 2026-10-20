import threading
import time
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from studio.l3_interface_adapters.gateways.prompt_rewriters import NoPromptRewriter
from studio.l4_frameworks_and_drivers.config import ConfigError, load_config
from studio.l4_frameworks_and_drivers.main import (
    assemble_studio,
    build_backends,
    build_rewriters,
    build_video_backends,
)
from tests.support.fakes import FakeBackendGateway


def settings(tmp_path: Path, text: str, **flags):
    path = tmp_path / "studio.toml"
    path.write_text(text)
    return load_config(path, **flags)


def test_only_the_offered_backends_are_built(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21"\n[qwen21]\nquantize = 0\n')
    assert list(build_backends(config)) == ["qwen21"]


def test_video_models_have_an_independent_default_and_visible_list(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21"\n'
        'default_video_backend = "ltx25"\n'
        'visible_video_backends = ["ltx25"]\n'
        "[qwen21]\nquantize = 0\n",
    )

    assert config.default_video_backend == "ltx25"
    assert config.visible_video_backends == ("ltx25",)
    assert list(build_video_backends(config)) == ["ltx25"]


def test_video_default_is_added_when_the_visible_list_omits_it(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21"\n'
        'default_video_backend = "ltx25"\n'
        'visible_video_backends = ["future-model"]\n'
        "[qwen21]\nquantize = 0\n",
    )

    assert config.visible_video_backends == ("ltx25", "future-model")


def test_a_video_backend_the_app_does_not_know_is_named(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21"\ndefault_video_backend = "mystery"\n[qwen21]\nquantize = 0\n',
    )

    with pytest.raises(ConfigError, match="no video backend called mystery"):
        build_video_backends(config)


def test_a_missing_setting_is_named(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21"\n[qwen21]\nquantize = 0\n', backend="flux2")
    with pytest.raises(ConfigError, match=r"model_dir under \[flux2\]"):
        build_backends(config)


def test_the_viggle_backend_offers_the_same_prompt_rewriters(tmp_path: Path):
    """The rewriters are models of their own and do not read the image engine, so a
    backend that draws the same model family offers them too. Leaving it out hid the
    toggle on a page that had every other control."""
    settings_text = (
        'default_backend = "viggle_turbo"\n'
        'visible_backends = ["qwen21", "viggle_turbo"]\n'
        "[qwen21]\nquantize = 0\n"
        '[viggle_turbo]\nquantize = 0\nlora_path = "turbo.safetensors"\n'
        'rewrite_generate_model = "Qwen/PE-T2I"\nrewrite_edit_model = "Qwen/PE-I2I"\n'
    )
    built = build_rewriters(settings(tmp_path, settings_text))
    assert built["viggle_turbo"].modes() == ("generate", "edit")


def test_a_backend_with_no_rewriter_settings_gets_none(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21"\n[qwen21]\nquantize = 0\n')
    assert build_rewriters(config)["qwen21"].modes() == ()


def test_an_unknown_backend_is_named(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "krea2"\n')
    with pytest.raises(ConfigError, match="no backend called krea2"):
        build_backends(config)


def test_the_viggle_backend_is_built_from_its_own_settings(tmp_path: Path):
    """The models are built here rather than in the backend package, because one
    backend package may not import another and Viggle drives qwen21's two models.
    Building one loads nothing."""
    config = settings(
        tmp_path,
        'default_backend = "viggle_turbo"\n[viggle_turbo]\nquantize = 0\nlora_path = "turbo.safetensors"\n',
    )
    assert list(build_backends(config)) == ["viggle_turbo"]


def test_the_viggle_backend_cannot_be_built_without_its_adapter_path(tmp_path: Path):
    """The path is required the way every other backend's settings are, so a file
    that names the backend and not its adapter says so."""
    config = settings(tmp_path, 'default_backend = "viggle_turbo"\n[viggle_turbo]\nquantize = 0\n')
    with pytest.raises(ConfigError, match=r"lora_path under \[viggle_turbo\]"):
        build_backends(config)


def test_official_turbo_backend_is_built_from_its_local_weight_directory(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21_turbo"\n[qwen21_turbo]\nquantize = 0\nmodel_dir = "weights/qwen-turbo"\n',
    )

    backend = build_backends(config)["qwen21_turbo"]

    assert backend.capabilities().backend_id == "qwen21_turbo"
    assert backend._model_dir == (tmp_path / "weights/qwen-turbo").resolve()


def test_official_turbo_needs_a_local_weight_directory_setting(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21_turbo"\n[qwen21_turbo]\nquantize = 0\n')

    with pytest.raises(ConfigError, match=r"model_dir under \[qwen21_turbo\]"):
        build_backends(config)


def test_official_turbo_gets_the_same_optional_prompt_rewriters(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21_turbo"\n'
        '[qwen21_turbo]\nquantize = 0\nmodel_dir = "weights"\n'
        'rewrite_generate_model = "Qwen/PE-T2I"\nrewrite_edit_model = "Qwen/PE-I2I"\n',
    )

    assert build_rewriters(config)["qwen21_turbo"].modes() == ("generate", "edit")


@pytest.fixture
def served():
    """A real server on a free port, over a backend whose run lasts until it is cancelled."""
    started = threading.Event()
    backend = FakeBackendGateway(stop_check=lambda step: started.set() or time.sleep(0.2))
    studio = assemble_studio({"fake": backend}, {"fake": NoPromptRewriter()}, "fake", ("fake",))
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server, backend, started
    server.shutdown()
    server.server_close()


def post(server, path, body=b"", **headers):
    url = f"http://127.0.0.1:{server.server_address[1]}{path}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.status, answer.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, ""


def test_shutdown_stops_the_run_before_it_frees_the_backend(served):
    """The frees wait in line on the GPU thread, behind any run, so a Ctrl-C that
    did not cancel first waited for the image to finish."""
    studio, server, backend, started = served
    answers = []
    run = threading.Thread(target=lambda: answers.append(post(server, "/generate", b"prompt=p&steps=50")))
    run.start()
    assert started.wait(5)
    began = time.monotonic()
    studio.shutdown()
    assert time.monotonic() - began < 2
    run.join(5)
    assert "Cancelled" in answers[0][1] and backend.events == ["release"]


def test_shutdown_without_a_rewriter_skips_unused_model_adapters(served):
    """The rewriter is optional, and an unused backend has no model memory to release."""
    studio, _, backend, _ = served
    replace(studio, rewriter=None).shutdown()
    assert backend.events == []


def test_the_two_mlx_packs_are_separate_video_backends(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21"\n'
        'default_video_backend = "ltx25_mlx"\n'
        'visible_video_backends = ["ltx25_mlx", "ltx23_mlx"]\n'
        "[qwen21]\nquantize = 0\n"
        '[mlx_video]\ncli_path = "/tmp/ltx-2-mlx"\n'
        'model_ltx25 = "pack-25"\nmodel_ltx23 = "pack-23"\n',
    )

    video = build_video_backends(config)

    assert list(video) == ["ltx25_mlx", "ltx23_mlx"]
    assert video["ltx25_mlx"].capabilities().name == "LTX-2.5 q8"
    assert video["ltx23_mlx"].capabilities().name == "LTX-2.3 q8"
    assert video["ltx25_mlx"]._runner._enhances is False
    assert video["ltx23_mlx"]._runner._enhances is True
    assert video["ltx25_mlx"]._runner._keyframe_two_stage is False
    assert video["ltx23_mlx"]._runner._keyframe_two_stage is True


def test_a_pack_without_its_model_setting_is_refused(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21"\n'
        'default_video_backend = "ltx25_mlx"\n'
        'visible_video_backends = ["ltx25_mlx"]\n'
        "[qwen21]\nquantize = 0\n"
        '[mlx_video]\ncli_path = "/tmp/ltx-2-mlx"\n',
    )

    with pytest.raises(ConfigError, match="model_ltx25"):
        build_video_backends(config)
