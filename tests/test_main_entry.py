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

SETTINGS = (
    'default_backend = "qwen21"\n'
    'visible_backends = ["qwen21"]\n'
    "[qwen21]\n"
    "quantize = 0\n"
    'edit_script = "qwen21/qwen21_edit.py"\n'
)


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
