"""Tests for the me dashboard."""

import subprocess
import sys

import pytest
from click.testing import CliRunner

from clustertool.cli import main
from clustertool.commands import me as me_cmd
from clustertool.tui import data


def test_me_does_not_import_textual_at_module_scope():
    """The extra is optional, so a site without it must still be able to run me."""
    code = "import sys, clustertool.commands.me; print('textual' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stdout


def test_me_plain_does_not_import_textual():
    code = (
        "import sys\n"
        "from click.testing import CliRunner\n"
        "from clustertool.cli import main\n"
        "CliRunner().invoke(main, ['me', '--plain'])\n"
        "print('textual' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip().endswith("False"), out.stdout


@pytest.mark.parametrize(
    ("user", "plain", "access", "tty", "expected"),
    [
        (None, False, False, True, True),
        (None, True, False, True, False),
        ("alice", False, False, True, False),
        (None, False, True, True, False),
        (None, False, False, False, False),
    ],
)
def test_wants_dashboard(monkeypatch, user, plain, access, tty, expected):
    """Naming a user, asking for access, or redirecting all fall back to one-shot."""
    monkeypatch.setattr(me_cmd.sys.stdout, "isatty", lambda: tty, raising=False)
    assert me_cmd._wants_dashboard(user, plain, access) is expected


def test_wants_dashboard_is_false_without_the_extra(monkeypatch):
    monkeypatch.setattr(me_cmd.sys.stdout, "isatty", lambda: True, raising=False)
    real = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def no_textual(name, *args, **kwargs):
        if name == "textual":
            raise ModuleNotFoundError(name)
        return real(name, *args, **kwargs)

    monkeypatch.setitem(__import__("builtins").__dict__, "__import__", no_textual)
    assert me_cmd._wants_dashboard(None, False, False) is False


def test_me_piped_matches_plain():
    """Redirected output must stay the one-shot summary a script can parse."""
    runner = CliRunner()
    assert runner.invoke(main, ["me"]).output == runner.invoke(main, ["me", "--plain"]).output


def test_identity_reads_the_uid_not_the_environment(monkeypatch):
    monkeypatch.setenv("USER", "someoneelse")
    monkeypatch.setattr(data, "site", type("S", (), {"qos_cluster": staticmethod(lambda: "c")}))
    who = data.identity()
    import os
    import pwd

    assert who.user == pwd.getpwuid(os.getuid()).pw_name
    assert who.host and "." not in who.host
