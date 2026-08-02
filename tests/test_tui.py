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
        assert app.focused.id == "jobs-table"
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
    from_widgets = {"up", "down"}
    bound = {binding[0] for binding in MeApp.BINDINGS} | from_widgets
    listed = {
        line.split()[0]
        for line in HELP.splitlines()
        if line.startswith("  ") and line.strip() and not line.strip().endswith(":")
    }
    unbound = {aliases.get(key, key) for key in listed} - bound
    assert unbound == set(), f"help lists unbound keys: {unbound}"


async def test_status_bar_sets_a_refresh_timer(monkeypatch):
    """Without the timer the clock freezes at whatever it read when the app started."""
    from clustertool.tui.panels.status import StatusBar

    intervals = []
    monkeypatch.setattr(
        StatusBar, "set_interval", lambda self, interval, callback: intervals.append(interval)
    )
    app = _app()
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
    assert intervals == [1.0]


async def test_storage_panel_keeps_a_usable_width_when_narrow():
    """Without a floor the storage column collapses to its border and shows nothing."""
    app = _app()
    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()
        assert app.query_one("#storage").region.width >= 24


def test_fit_keeps_the_clock_and_the_user_at_any_width():
    """The bar exists to say who and when, so those two survive every other field."""
    from clustertool.tui.panels.status import fit

    who = data.Identity("mmsh", "Maria Fernanda Gutierrez", "holy8a26105", "Kempner AI Cluster")
    stamp = "Sun 2026-08-02 14:32"
    for width in (120, 100, 80, 60, 45, 40):
        line = fit(who, stamp, width)
        assert len(line) <= width, (width, line)
        assert stamp in line, (width, line)
        assert "mmsh" in line, (width, line)


def test_fit_sheds_the_site_name_before_the_full_name():
    from clustertool.tui.panels.status import fit

    who = data.Identity("mmsh", "A Name", "host01", "A Very Long Site Name Indeed")
    line = fit(who, "Sun 2026-08-02 14:32", 60)
    assert "A Name" in line
    assert "Very Long Site" not in line


@pytest.mark.parametrize(
    "hostile",
    ["Ann [Bo] Cee", "[bold red]Boom[/]", "Ann [/] Cee", "[/bold]"],
)
async def test_a_bracket_in_a_name_does_not_break_the_bar(hostile):
    """A full name comes from GECOS and a site name from config, so neither is trusted.

    An unmatched closing tag raised while painting, which took down the app at
    startup, so this has to reach the compositor rather than only call render.
    """
    from clustertool.tui.app import MeApp

    app = MeApp(
        identity=data.Identity("alice", hostile, "node01", "Cluster [/prod]"),
        clock=lambda: FIXED_CLOCK,
    )
    async with app.run_test(size=(100, 12)) as pilot:
        await pilot.pause()
        assert hostile in str(app.query_one("#status").render())


SAMPLE_JOBS = [
    data.JobRow(
        "111", "RUNNING", "kempner_h100", 4, "2:14:00", "None", ["gpu8a15", "gpu8a16"], "gres/gpu=4"
    ),
    data.JobRow("222", "PENDING", "kempner", 4, "0:00", "Priority", [], "gres/gpu=4"),
]


def test_jobs_asks_for_the_allocation_and_a_separator(monkeypatch):
    """The default format pads to fixed widths and truncates a long TRES string."""
    import clustertool.process as proc

    seen = []
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, "", ""))[1])
    data.jobs("alice")
    joined = " ".join(seen[0])
    assert "tres-alloc" in joined
    assert "JobID:|" in joined


def test_jobs_parses_a_pending_and_a_running_row(monkeypatch):
    import clustertool.process as proc

    out = (
        "111|RUNNING|kempner_h100|2:14:00|None|cpu=96,gres/gpu=4|gpu8a[15-16]|\n"
        "222|PENDING|kempner|0:00|Priority|cpu=64,gres/gpu=4||\n"
    )
    import clustertool.slurm as slurm_module

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, out, ""))
    monkeypatch.setattr(
        slurm_module, "expand_hostlist", lambda nl: ["gpu8a15", "gpu8a16"] if nl else []
    )
    rows = data.jobs("alice")
    assert [r.jobid for r in rows] == ["111", "222"]
    assert rows[0].gpus == 4
    assert rows[1].pending and not rows[0].pending
    assert rows[1].where == "(Priority)"


def test_jobs_raises_rather_than_reporting_none(monkeypatch):
    """An empty list would read as having no jobs, which is a different fact."""
    import clustertool.process as proc

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (1, "", "slurmctld down"))
    with pytest.raises(data.CommandError, match="could not read your jobs"):
        data.jobs("alice")


def test_where_names_the_node_or_the_wait():
    one = data.JobRow("1", "RUNNING", "p", 0, "1:00", "None", ["n1"], "")
    many = data.JobRow("1", "RUNNING", "p", 0, "1:00", "None", ["n1", "n2", "n3"], "")
    waiting = data.JobRow("1", "PENDING", "p", 0, "0:00", "Resources", [], "")
    unknown = data.JobRow("1", "PENDING", "p", 0, "0:00", "None", [], "")
    assert one.where == "n1"
    assert many.where == "n1 +2"
    assert waiting.where == "(Resources)"
    assert unknown.where == "-"


async def test_arrow_keys_move_the_detail():
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(100, 22)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show(SAMPLE_JOBS)
        await pilot.pause()
        assert panel.selected.jobid == "111"
        assert "kempner_h100" in panel._detail_text()
        await pilot.press("down")
        await pilot.pause()
        assert panel.selected.jobid == "222"
        assert "waiting: Priority" in panel._detail_text()


async def test_an_empty_table_says_no_jobs_not_nothing():
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(100, 22)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show([])
        await pilot.pause()
        assert panel.selected is None
        assert "No jobs" in panel._detail_text()


async def test_a_failed_refresh_keeps_the_rows_and_says_so():
    """A scheduler hiccup must leave the panel stale, not looking like an empty queue."""
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(100, 22)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show(SAMPLE_JOBS)
        await pilot.pause()
        panel.fail("controller busy")
        await pilot.pause()
        text = panel._detail_text()
        assert "stale: controller busy" in text
        assert "111" in text


async def test_the_cursor_survives_a_refresh():
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(100, 22)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show(SAMPLE_JOBS)
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        panel.show(SAMPLE_JOBS)
        await pilot.pause()
        assert panel.selected.jobid == "222"
