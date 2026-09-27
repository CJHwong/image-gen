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
from studio.l4_frameworks_and_drivers.main import assemble_studio, build_backends
from tests.support.fakes import FakeBackendGateway


def settings(tmp_path: Path, text: str, **flags):
    path = tmp_path / "studio.toml"
    path.write_text(text)
    return load_config(path, **flags)


def test_only_the_offered_backends_are_built(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21"\n[qwen21]\nedit_script = "edit.py"\n')
    assert list(build_backends(config)) == ["qwen21"]


def test_a_missing_setting_is_named(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21"\n[qwen21]\nedit_script = "edit.py"\n', backend="flux2")
    with pytest.raises(ConfigError, match=r"model_dir under \[flux2\]"):
        build_backends(config)


def test_an_unknown_backend_is_named(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "krea2"\n')
    with pytest.raises(ConfigError, match="no backend called krea2"):
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
