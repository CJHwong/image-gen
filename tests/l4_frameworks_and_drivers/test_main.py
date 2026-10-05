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
from studio.l4_frameworks_and_drivers.main import assemble_studio, build_backends, build_rewriters
from tests.support.fakes import FakeBackendGateway


def settings(tmp_path: Path, text: str, **flags):
    path = tmp_path / "studio.toml"
    path.write_text(text)
    return load_config(path, **flags)


def test_only_the_offered_backends_are_built(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21"\n[qwen21]\nquantize = 0\n')
    assert list(build_backends(config)) == ["qwen21"]


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


def test_shutdown_without_a_rewriter_still_frees_the_backends(served):
    """The rewriter is optional: a settings file that names no rewrite model leaves it
    None, and the page hides the toggle. Shutdown must free the backends and skip the
    rewriter rather than trip over it."""
    studio, _, backend, _ = served
    replace(studio, rewriter=None).shutdown()
    assert backend.events == ["release"]
