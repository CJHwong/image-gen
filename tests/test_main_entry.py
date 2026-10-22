"""The command line entry, `studio/__main__.py`.

Its mirrored path would be `tests/__main__.py`, and pytest never collects that
name: `__main__.py` is the file pytest runs to start a session, so a test
written in it would not run. The test lives here instead.
"""

import runpy
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import studio.__main__ as entry
from studio.l4_frameworks_and_drivers import engines
from studio.l4_frameworks_and_drivers.config import load_config

SETTINGS = 'default_backend = "qwen21"\nvisible_backends = ["qwen21"]\n[qwen21]\nquantize = 0\n'

# The same, with the two rewriters named. A settings file written before they
# existed has no such keys and must still boot.
SETTINGS_WITH_REWRITERS = SETTINGS + 'rewrite_generate_model = "Qwen/PE-T2I"\nrewrite_edit_model = "Qwen/PE-I2I"\n'


def settings_file(tmp_path: Path, text: str = SETTINGS) -> Path:
    path = tmp_path / "studio.toml"
    path.write_text(text)
    return path


def argv(monkeypatch, *flags: str) -> None:
    monkeypatch.setattr(sys, "argv", ["studio", *flags])


def exit_message(exits) -> str:
    """The text `sys.exit` was given. `SystemExit.code` is an int when the call
    passed no message, and every path here passes one."""
    return str(exits.value.code)


def test_a_good_run_serves_until_ctrl_c_then_frees_the_engine(tmp_path, monkeypatch, capsys):
    """Ctrl-C is the documented way to stop, so it has to return the model and
    close the socket before the process ends."""
    server = Mock()
    server.serve_forever.side_effect = KeyboardInterrupt
    server_class = Mock(return_value=server)
    monkeypatch.setattr(entry, "ThreadingHTTPServer", server_class)
    argv(monkeypatch, "--stub", "--config", str(settings_file(tmp_path)), "--port", "8931")

    assert entry.main() is None

    assert server_class.call_args.args[0] == ("127.0.0.1", 8931)
    server.serve_forever.assert_called_once_with()
    server.server_close.assert_called_once_with()
    printed = capsys.readouterr().out
    assert "Ready on http://127.0.0.1:8931" in printed and "Stopped." in printed
    assert "Models load on first use" in printed and "Loading Qwen" not in printed


def test_the_startup_line_names_the_rewriters_before_the_click(tmp_path, monkeypatch, capsys):
    """The first rewrite in a mode fetches about 19 GB with the progress bar off, so
    the page looks merely busy. The wait has to be visible before the button is pressed."""
    server = Mock()
    server.serve_forever.side_effect = KeyboardInterrupt
    monkeypatch.setattr(entry, "ThreadingHTTPServer", Mock(return_value=server))
    argv(monkeypatch, "--stub", "--config", str(settings_file(tmp_path, SETTINGS_WITH_REWRITERS)), "--port", "8932")

    assert entry.main() is None

    printed = capsys.readouterr().out
    line = next(row for row in printed.splitlines() if row.startswith("Rewriters: "))
    assert line.startswith("Rewriters: generate ")
    assert ", edit " in line
    # The cache note appears before the ready line, before the user tries a rewrite.
    assert printed.index("Rewriters: ") < printed.index("Ready on http://127.0.0.1:8932")


def test_a_backend_with_no_rewriter_prints_no_line(tmp_path):
    """A backend that offers no rewriter has no wait to warn about."""
    path = settings_file(tmp_path, 'default_backend = "flux2"\nvisible_backends = ["qwen21"]\n')
    assert entry.rewriter_cache_line(load_config(path)) == ""


def test_a_settings_file_without_rewriter_keys_prints_no_line(tmp_path):
    """A file written before the rewriters existed boots as it did, with no toggle."""
    assert entry.rewriter_cache_line(load_config(settings_file(tmp_path))) == ""


def test_bad_settings_exit_with_the_message_that_names_the_file(tmp_path, monkeypatch):
    """The user has to learn which file and which key are wrong, so the exit
    message carries both."""
    path = settings_file(tmp_path, 'default_backend = "krea2"\n')
    argv(monkeypatch, "--stub", "--config", str(path))

    with pytest.raises(SystemExit) as exits:
        entry.main()

    message = exit_message(exits)
    assert message.startswith(f"Bad settings in {path}: ")
    assert "no backend called krea2" in message


def test_a_machine_with_no_engine_exits_before_the_port_is_bound(tmp_path, monkeypatch):
    """The refusal comes first, so a host that cannot run a model never occupies
    the port and never makes the user wait for a load that cannot happen."""
    server_class = Mock()
    monkeypatch.setattr(engines, "mlx_available", lambda: False)
    monkeypatch.setattr(entry, "ThreadingHTTPServer", server_class)
    argv(monkeypatch, "--config", str(settings_file(tmp_path)))

    with pytest.raises(SystemExit) as exits:
        entry.main()

    message = exit_message(exits)
    assert message.startswith("Cannot run here: no MLX GPU is available")
    assert "PORTABILITY.md" in message  # the message names the remedy
    server_class.assert_not_called()


def test_a_busy_port_exits_with_the_message_that_names_the_flag(tmp_path, monkeypatch):
    """A taken port fails before the page starts, and the message names the fix."""
    monkeypatch.setattr(entry, "ThreadingHTTPServer", Mock(side_effect=OSError(48, "Address already in use")))
    argv(monkeypatch, "--stub", "--config", str(settings_file(tmp_path)), "--port", "8765")

    with pytest.raises(SystemExit) as exits:
        entry.main()

    assert exit_message(exits) == (
        "Cannot bind 127.0.0.1:8765 ([Errno 48] Address already in use). Pass --port for a free one."
    )


def test_startup_does_not_load_or_prewarm_a_model(tmp_path, monkeypatch, capsys):
    """The server starts without model memory; the first run loads its model."""
    studio = SimpleNamespace(handler=Mock(), shutdown=Mock())
    server = Mock()
    server.serve_forever.side_effect = KeyboardInterrupt
    monkeypatch.setattr(entry, "create_studio", Mock(return_value=studio))
    monkeypatch.setattr(entry, "ThreadingHTTPServer", Mock(return_value=server))
    argv(monkeypatch, "--config", str(settings_file(tmp_path)))

    assert entry.main() is None

    studio.shutdown.assert_called_once_with()
    printed = capsys.readouterr().out
    assert "Ready on http://127.0.0.1:8765" in printed
    assert "Models load on first use" in printed


def test_running_the_package_as_a_script_reaches_main(tmp_path, monkeypatch):
    """`python -m studio` starts the server through the guard at the bottom of
    the file. `uv run studio` goes through the console script instead, so this is
    the only way to run that line."""
    path = settings_file(tmp_path, 'default_backend = "krea2"\n')
    argv(monkeypatch, "--stub", "--config", str(path))

    # runpy says so itself: this file is already in sys.modules, because the
    # tests above import it. The re-execution is the point of the test.
    with warnings.catch_warnings(), pytest.raises(SystemExit) as exits:
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("studio", run_name="__main__")

    assert "no backend called krea2" in exit_message(exits)


def test_the_full_precision_flag_reaches_the_settings_file(tmp_path, monkeypatch):
    """`-q 0` is the documented way to load the full precision weights, and the settings reader
    has always treated a zero as no quantization, so the flag has to accept it. It refused it
    until 2026-10-19, which made two documented commands fail at argparse."""
    seen = {}

    def fake_load_config(path, backend=None, quantize=None, visible=None, visible_video=None, visible_voice=None):
        seen["quantize"] = quantize
        raise SystemExit(0)

    monkeypatch.setattr(entry, "load_config", fake_load_config)
    argv(monkeypatch, "--stub", "--config", str(settings_file(tmp_path)), "-q", "0")

    with pytest.raises(SystemExit):
        entry.main()

    assert seen["quantize"] == 0


def test_the_all_backends_flag_offers_every_model_the_studio_can_build(tmp_path, monkeypatch):
    """A settings file that offers one model hides the page's picker, which is the default. The
    flag is how a person asks for the lot without editing the file, and what it hands over is
    the registry's own list, so a backend added later is offered by the same flag."""
    seen = {}

    def fake_load_config(path, backend=None, quantize=None, visible=None, visible_video=None, visible_voice=None):
        seen["visible"] = visible
        seen["visible_video"] = visible_video
        seen["visible_voice"] = visible_voice
        raise SystemExit(0)

    monkeypatch.setattr(entry, "load_config", fake_load_config)
    argv(monkeypatch, "--stub", "--config", str(settings_file(tmp_path)), "--all-backends")

    with pytest.raises(SystemExit):
        entry.main()

    assert seen["visible"] == tuple(entry.BACKENDS)
    assert "flux2" in seen["visible"]
    assert seen["visible_video"] == tuple(entry.VIDEO_BACKENDS)
    assert seen["visible_voice"] == tuple(entry.VOICE_BACKENDS)


def test_the_all_backends_flag_includes_installed_plugins(tmp_path, monkeypatch):
    """A settings file that offers one model hides the page's picker, which is the default. The
    flag is how a person asks for the lot without editing the file, and what it hands over is
    the registry's own list, so a backend added later is offered by the same flag."""
    seen = {}
    monkeypatch.setattr(
        entry, "discover_plugins", lambda: type("Plugins", (), {"ids": lambda self, kind: ("external_" + kind,)})()
    )

    def fake_load_config(path, backend=None, quantize=None, visible=None, visible_video=None, visible_voice=None):
        seen["visible"] = visible
        seen["visible_video"] = visible_video
        seen["visible_voice"] = visible_voice
        raise SystemExit(0)

    monkeypatch.setattr(entry, "load_config", fake_load_config)
    argv(monkeypatch, "--stub", "--config", str(settings_file(tmp_path)), "--all-backends")

    with pytest.raises(SystemExit):
        entry.main()

    assert seen["visible"] == (*entry.BACKENDS, "external_image")
    assert "flux2" in seen["visible"]
    assert seen["visible_video"] == (*entry.VIDEO_BACKENDS, "external_video")
    assert seen["visible_voice"] == (*entry.VOICE_BACKENDS, "external_voice")


def test_without_the_flag_the_settings_file_decides_what_is_offered(tmp_path, monkeypatch):
    seen = {}

    def fake_load_config(path, backend=None, quantize=None, visible=None, visible_video=None, visible_voice=None):
        seen["visible"] = visible
        seen["visible_video"] = visible_video
        seen["visible_voice"] = visible_voice
        raise SystemExit(0)

    monkeypatch.setattr(entry, "load_config", fake_load_config)
    argv(monkeypatch, "--stub", "--config", str(settings_file(tmp_path)))

    with pytest.raises(SystemExit):
        entry.main()

    assert seen["visible"] is None
    assert seen["visible_video"] is None
    assert seen["visible_voice"] is None


def test_a_named_list_of_backends_is_what_the_page_offers(tmp_path):
    """The loader takes the list outright for the flag above, and the default still comes from
    the file when it is not handed one."""
    path = settings_file(tmp_path)

    assert load_config(path).visible_backends == ("qwen21",)
    assert load_config(path, visible=("flux2", "qwen21")).visible_backends == ("flux2", "qwen21")
