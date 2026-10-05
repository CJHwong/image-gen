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
    assert "Loading Qwen-Image-2.1 (bf16)." in printed
    assert "Ready on http://127.0.0.1:8931" in printed and "Stopped." in printed


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
    # Above the loading line, so it is read before the wait it warns about starts.
    assert printed.index("Rewriters: ") < printed.index("Loading Qwen-Image-2.1")


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
    assert message.startswith("Cannot run here: no MLX on this machine")
    assert "PORTABILITY.md" in message  # the message names the remedy
    server_class.assert_not_called()


def test_a_busy_port_exits_with_the_message_that_names_the_flag(tmp_path, monkeypatch):
    """The bind happens before the load, so a taken port costs a second instead
    of the minute a weight load takes. The message has to say what to do next."""
    monkeypatch.setattr(entry, "ThreadingHTTPServer", Mock(side_effect=OSError(48, "Address already in use")))
    argv(monkeypatch, "--stub", "--config", str(settings_file(tmp_path)), "--port", "8765")

    with pytest.raises(SystemExit) as exits:
        entry.main()

    assert exit_message(exits) == (
        "Cannot bind 127.0.0.1:8765 ([Errno 48] Address already in use). Pass --port for a free one."
    )


def test_a_model_that_will_not_load_exits_with_the_error(tmp_path, monkeypatch, capsys):
    """A load failure reaches the user as one line, not as a traceback under a
    server that never answers."""
    studio = Mock()
    studio.active_capabilities.return_value = SimpleNamespace(name="Qwen-Image-2.1", badge="int4")
    studio.prepare.execute.side_effect = RuntimeError("out of memory")
    monkeypatch.setattr(entry, "create_studio", Mock(return_value=studio))
    monkeypatch.setattr(entry, "ThreadingHTTPServer", Mock(return_value=Mock()))
    argv(monkeypatch, "--config", str(settings_file(tmp_path)))

    with pytest.raises(SystemExit) as exits:
        entry.main()

    assert exit_message(exits) == "Could not load the model: out of memory"
    assert "Loading Qwen-Image-2.1 (int4)." in capsys.readouterr().out


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
