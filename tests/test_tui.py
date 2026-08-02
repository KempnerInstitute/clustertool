"""Tests for the me dashboard."""

import builtins
import datetime
import os
import pwd
import socket
import subprocess
import sys

import pytest
from click.testing import CliRunner

from clustertool import slurm
from clustertool.cli import main
from clustertool.commands import me as me_cmd
from clustertool.tui import data


def test_me_does_not_import_textual_at_module_scope():
    """The extra is optional, so a site without it must still be able to run me."""
    code = "import sys, clustertool.commands.me; print('textual' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stdout


def test_the_data_layer_does_not_import_textual():
    """Panel data is tested without starting an app, so it must load without the extra."""
    code = "import sys, clustertool.tui.data; print('textual' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stdout


def test_me_dispatches_to_the_dashboard(monkeypatch):
    """Without this the whole dispatch could be deleted and the suite stay green."""
    import clustertool.tui.app as app_module

    calls = []
    monkeypatch.setattr(app_module, "run", lambda: calls.append(1))
    monkeypatch.setattr(me_cmd, "_wants_dashboard", lambda user, plain, access: True)
    me_cmd.me.callback(user=None, plain=False, access=False)
    assert calls == [1]


def test_me_prints_the_summary_when_the_dashboard_is_not_wanted(monkeypatch):
    import clustertool.tui.app as app_module

    calls = []
    monkeypatch.setattr(app_module, "run", lambda: calls.append(1))
    monkeypatch.setattr(me_cmd, "_wants_dashboard", lambda user, plain, access: False)
    monkeypatch.setattr(slurm, "my_jobs", lambda user: [])
    monkeypatch.setattr(slurm, "user_gpu_count", lambda user: 0)
    monkeypatch.setattr(slurm, "user_fairshare", lambda user: [])
    result = CliRunner().invoke(main, ["me", "--plain"])
    assert result.exit_code == 0
    assert "overview for" in result.output
    assert calls == []


def test_me_falls_back_when_the_extra_is_missing(monkeypatch):
    """A textual that cannot be imported must print the summary, not traceback."""
    monkeypatch.setattr(me_cmd, "_wants_dashboard", lambda user, plain, access: True)
    real = builtins.__import__

    def no_tui(name, *args, **kwargs):
        if name == "clustertool.tui.app":
            raise ImportError("textual missing")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_tui)
    monkeypatch.setattr(slurm, "my_jobs", lambda user: [])
    monkeypatch.setattr(slurm, "user_gpu_count", lambda user: 0)
    monkeypatch.setattr(slurm, "user_fairshare", lambda user: [])
    result = CliRunner().invoke(main, ["me"])
    assert result.exit_code == 0
    assert "overview for" in result.output


@pytest.mark.parametrize(
    ("user", "plain", "access", "stdout_tty", "stdin_tty", "term", "expected"),
    [
        (None, False, False, True, True, "xterm", True),
        (None, True, False, True, True, "xterm", False),
        ("alice", False, False, True, True, "xterm", False),
        (None, False, True, True, True, "xterm", False),
        (None, False, False, False, True, "xterm", False),
        (None, False, False, True, False, "xterm", False),
        (None, False, False, True, True, "dumb", False),
        (None, False, False, True, True, "", False),
    ],
)
def test_wants_dashboard(monkeypatch, user, plain, access, stdout_tty, stdin_tty, term, expected):
    """A terminal on stdout alone would draw an app no keypress could reach."""
    monkeypatch.setenv("TERM", term)
    monkeypatch.setattr(me_cmd.sys, "stdout", type("S", (), {"isatty": lambda self: stdout_tty})())
    monkeypatch.setattr(me_cmd.sys, "stdin", type("S", (), {"isatty": lambda self: stdin_tty})())
    assert me_cmd._wants_dashboard(user, plain, access) is expected


def test_caller_reports_a_missing_passwd_entry(monkeypatch):
    """A uid with no passwd entry happens in a container, and must not traceback."""
    import click

    def boom(uid):
        raise KeyError("getpwuid(): uid not found: 12345")

    monkeypatch.setattr(me_cmd.pwd, "getpwuid", boom)
    with pytest.raises(click.UsageError, match="could not determine who you are"):
        me_cmd._caller()


def test_identity_reads_the_uid_not_the_environment(monkeypatch):
    monkeypatch.setenv("USER", "someoneelse")
    monkeypatch.setattr(socket, "gethostname", lambda: "node01.example.edu")
    monkeypatch.setattr(data.site, "site_name", lambda: "Example HPC")
    monkeypatch.setattr(slurm, "user_fullnames", lambda users: {users[0]: "A Name"})
    who = data.identity()
    assert who.user == pwd.getpwuid(os.getuid()).pw_name
    assert who.host == "node01"
    assert who.site_name == "Example HPC"
    assert who.full_name == "A Name"


def test_identity_survives_a_failed_name_lookup(monkeypatch):
    """getent is not on every host, and a missing full name is not worth an error."""
    monkeypatch.setattr(socket, "gethostname", lambda: "node01")
    monkeypatch.setattr(data.site, "site_name", lambda: "Example HPC")

    def boom(users):
        raise data.CommandError("getent not found")

    monkeypatch.setattr(slurm, "user_fullnames", boom)
    assert data.identity().full_name == ""


@pytest.mark.asyncio
async def test_app_renders_the_identity_and_quits():
    """The shell must start, show who you are, and exit cleanly on the quit key."""
    from clustertool.tui.app import MeApp

    app = MeApp(identity=data.Identity("alice", "A Name", "node01", "Example HPC"))
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        assert "alice (A Name) @ node01" in str(app.query_one("#status").render())
        assert "Example HPC" in str(app.query_one("#status").render())
        await pilot.press("Q")
    assert app.return_code == 0


@pytest.mark.asyncio
async def test_app_omits_empty_parentheses_without_a_full_name():
    from clustertool.tui.app import MeApp

    app = MeApp(identity=data.Identity("alice", "", "node01", "Example HPC"))
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        assert "()" not in str(app.query_one("#status").render())
        await pilot.press("Q")


def test_run_starts_the_app(monkeypatch):
    from clustertool.tui import app as app_module

    started = []
    monkeypatch.setattr(app_module.MeApp, "run", lambda self: started.append(self))
    app_module.run(identity=data.Identity("alice", "", "node01", "Example HPC"))
    assert len(started) == 1


FIXED_CLOCK = datetime.datetime(2026, 8, 2, 14, 32)


def _app(full_name="A Name"):
    from clustertool.tui.app import MeApp

    return MeApp(
        identity=data.Identity("alice", full_name, "node01", "Example HPC"),
        clock=lambda: FIXED_CLOCK,
    )


async def test_shell_shows_three_panels_and_the_status_bar():
    app = _app()
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        titles = [
            str(app.query_one(f"#{name}").border_title) for name in ("jobs", "storage", "standing")
        ]
        assert titles == ["Jobs", "Storage", "Standing"]
        assert "alice (A Name) @ node01" in str(app.query_one("#status").render())


async def test_status_bar_shows_the_clock():
    """The clock is injected so a snapshot does not change every minute."""
    app = _app()
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        assert "Sun 2026-08-02 14:32" in str(app.query_one("#status").render())


async def test_tab_cycles_the_panels():
    app = _app()
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        assert app.focused.id == "jobs"
        await pilot.press("tab")
        assert app.focused.id == "storage"
        await pilot.press("tab")
        assert app.focused.id == "standing"


async def test_help_opens_and_closes():
    app = _app()
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        assert "tab" in str(app.screen.query_one("#help-body").render())
        await pilot.press("escape")
        await pilot.pause()
        assert not app.screen.query("#help-body")


async def test_the_status_bar_survives_a_short_terminal():
    """It is the one thing that must never be pushed off screen."""
    app = _app()
    async with app.run_test(size=(100, 6)) as pilot:
        await pilot.pause()
        bar = app.query_one("#status")
        assert bar.region.height == 1
        assert bar.region.y == 5


def test_help_lists_only_keys_that_are_bound():
    """Help that advertises a key doing nothing is worse than no help."""
    from clustertool.tui.app import HELP, MeApp

    aliases = {"?": "question_mark"}
    bound = {binding[0] for binding in MeApp.BINDINGS}
    listed = {
        line.split()[0]
        for line in HELP.splitlines()
        if line.startswith("  ") and line.strip() and not line.strip().endswith(":")
    }
    unbound = {aliases.get(key, key) for key in listed} - bound
    assert unbound == set(), f"help lists unbound keys: {unbound}"
