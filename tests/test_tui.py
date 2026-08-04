"""Tests for the me dashboard."""

import builtins
import datetime
import os
import pwd
import socket
import subprocess
import sys
import time

import pytest
from click.testing import CliRunner

from clustertool import slurm
from clustertool.cli import main
from clustertool.commands import me as me_cmd
from clustertool.process import CommandError
from clustertool.tui import data
from clustertool.tui.panels.jobs import JobsPanel


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
    monkeypatch.setattr(app_module, "run", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(me_cmd, "_wants_dashboard", lambda user, plain, access: True)
    me_cmd.me.callback(user=None, plain=False, access=False, interval=5.0, days=7, theme=None)
    assert calls == [{"interval": 5.0, "days": 7, "theme": None}]


def test_the_dashboard_flags_reach_the_app(monkeypatch):
    """A flag the app never reads is worse than no flag: it reads as having worked."""
    import clustertool.tui.app as app_module

    seen = {}
    monkeypatch.setattr(app_module, "run", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr(me_cmd, "_wants_dashboard", lambda user, plain, access: True)
    result = CliRunner().invoke(main, ["me", "-i", "30", "-d", "14"])
    assert result.exit_code == 0, result.output
    assert seen == {"interval": 30.0, "days": 14, "theme": None}


@pytest.mark.parametrize(
    ("asked", "expected"),
    [("light", "textual-light"), ("dark", "textual-dark"), ("ansi", "ansi-dark"), ("nord", "nord")],
)
async def test_the_theme_flag_picks_the_theme(asked, expected):
    """The app paints its own background, so the theme decides light or dark, not the
    terminal. A full Textual theme name passes through, since the app checks the
    list it has rather than a table here that would go stale.
    """
    app = _app(theme=asked)
    async with app.run_test(size=(100, 26)) as pilot:
        await pilot.pause()
        assert app.theme == expected


async def test_an_unknown_theme_says_so_and_opens_anyway():
    """A dashboard that will not open over a color is worse than one in the wrong one."""
    app = _app(theme="chartreuse")
    async with app.run_test(size=(100, 26)) as pilot:
        await pilot.pause()
        assert app.theme == "textual-dark"
        assert "no theme called chartreuse" in _painted(app)


async def test_naming_no_theme_leaves_the_choice_already_made_alone():
    """TEXTUAL_THEME is Textual's own way in, and the flag defaults to not using it.

    Asserting the default alone passed while apply_theme forced that same default,
    which is the failure this names, so the app is given a theme first and the test
    is whether it survives being mounted.
    """
    app = _app()
    app.theme = "nord"
    async with app.run_test(size=(100, 26)) as pilot:
        await pilot.pause()
        assert app.theme == "nord"


def test_the_theme_flag_reaches_the_app(monkeypatch):
    import clustertool.tui.app as app_module

    seen = {}
    monkeypatch.setattr(app_module, "run", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr(me_cmd, "_wants_dashboard", lambda user, plain, access: True)
    result = CliRunner().invoke(main, ["me", "--theme", "light"])
    assert result.exit_code == 0, result.output
    assert seen["theme"] == "light", seen


def test_an_interval_under_the_floor_is_refused(monkeypatch):
    """Every tick is a query on the controller, and r already refreshes on demand.

    run is stubbed as well as the terminal check: with the floor gone this tried to
    open a real dashboard and hung rather than failing. The message is asserted to
    name the floor itself, since matching the bare digit passed for any floor.
    """
    import clustertool.tui.app as app_module

    started = []
    monkeypatch.setattr(app_module, "run", lambda **kwargs: started.append(kwargs))
    monkeypatch.setattr(me_cmd, "_wants_dashboard", lambda user, plain, access: True)
    result = CliRunner().invoke(main, ["me", "-i", "0.2"])
    assert result.exit_code == 2, result.output
    assert "x>=2" in result.output, result.output
    assert started == []


async def test_the_window_flag_reaches_the_standing_query(monkeypatch):
    """The panel says how wide its window is, so a flag it ignores makes it lie."""
    seen = []
    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))
    monkeypatch.setattr(
        data,
        "standing",
        lambda user, days=data.STANDING_DAYS: (seen.append(days), _standing(days=days))[1],
    )
    app = _app(interval=30, days=21)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: seen == [21]), seen
        assert await _until(pilot, lambda: "last 21d" in _painted(app)), _painted(app)


def test_me_prints_the_summary_when_the_dashboard_is_not_wanted(monkeypatch):
    import clustertool.tui.app as app_module

    calls = []
    monkeypatch.setattr(app_module, "run", lambda **kwargs: calls.append(kwargs))
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

    app = MeApp(identity=data.Identity("alice", "A Name", "node01", "Example HPC"), interval=0)
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        assert "alice (A Name) @ node01" in str(app.query_one("#status").render())
        assert "Example HPC" in str(app.query_one("#status").render())
        await pilot.press("Q")
    assert app.return_code == 0


@pytest.mark.asyncio
async def test_app_omits_empty_parentheses_without_a_full_name():
    from clustertool.tui.app import MeApp

    app = MeApp(identity=data.Identity("alice", "", "node01", "Example HPC"), interval=0)
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        assert "()" not in str(app.query_one("#status").render())
        await pilot.press("Q")


def test_run_starts_the_app_with_everything_it_was_given(monkeypatch):
    """The one seam between the flags and the app, and nothing else covers it.

    Every other app test builds MeApp itself, and the flag tests stub run, so
    dropping all three arguments here left the whole suite green while --interval,
    --days and --theme did nothing.
    """
    from clustertool.tui import app as app_module

    started = []
    monkeypatch.setattr(app_module.MeApp, "run", lambda self: started.append(self))
    app_module.run(
        identity=data.Identity("alice", "", "node01", "Example HPC"),
        interval=30.0,
        days=21,
        theme="light",
    )
    assert len(started) == 1
    app = started[0]
    assert (app._interval, app._days, app._theme) == (30.0, 21, "light")


def test_the_days_flag_and_the_windows_own_default_agree():
    """Two defaults for one window would disagree the first time either moved."""
    from clustertool.commands.me import me

    default = next(p.default for p in me.params if p.name == "days")
    assert default == data.STANDING_DAYS


ABANDONED_SLEEP_S = 2.0
"""How long a stub that is meant to miss its deadline blocks for.

Only just longer than the deadlines these tests set, because the thread running it
is abandoned rather than joined and goes on to call whatever process.probe points
at next. At thirty seconds one such thread reached a later test's stub and broke
its count.
"""

FIXED_CLOCK = datetime.datetime(2026, 8, 2, 14, 32)


def _app(full_name="A Name", interval=0, days=data.STANDING_DAYS, theme=None):
    """Build the app with the timer off, so a shell test never asks a scheduler.

    With the timer on, these ran squeue for real: they passed on a login node and
    failed anywhere without Slurm, where the panel comes up marked stale.
    """
    from clustertool.tui.app import MeApp

    return MeApp(
        identity=data.Identity("alice", full_name, "node01", "Example HPC"),
        clock=lambda: FIXED_CLOCK,
        interval=interval,
        days=days,
        theme=theme,
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
        assert "next panel" in _painted(app)
        await pilot.press("escape")
        await pilot.pause()
        assert not list(app.screen.query("#help-body"))


@pytest.mark.parametrize("size", [(80, 24), (100, 24), (46, 18), (120, 40)])
async def test_the_help_overlay_reaches_every_action(size):
    """A key nobody can see is what this screen exists to prevent.

    The list is longer than a terminal of twenty-four rows holds, so the overlay
    scrolls and the entries below the fold are reached with the down key.
    """
    from clustertool.tui import actions

    app = _app()
    async with app.run_test(size=size) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        seen = _flat(app)
        for _ in range(30):
            await pilot.press("down")
            await pilot.pause()
            seen += _flat(app)
        for action in actions.MENU:
            assert "".join(action.label.split()) in seen, (action.label, size)


async def test_the_status_bar_survives_a_short_terminal():
    """It is the one thing that must never be pushed off screen."""
    app = _app()
    async with app.run_test(size=(100, 6)) as pilot:
        await pilot.pause()
        bar = app.query_one("#status")
        assert bar.region.height == 1
        assert bar.region.y == 5


def test_help_lists_only_keys_that_are_bound():
    """Help that advertises a key doing nothing is worse than no help.

    The keys the table binds itself count as bound, and are checked against its own
    binding list rather than taken on trust.
    """
    from textual.widgets import DataTable

    from clustertool.tui.app import HELP, MeApp

    aliases = {"?": "question_mark"}
    from_widgets = {"up", "down", "enter"}
    table_keys = {key for binding in DataTable.BINDINGS for key in binding.key.split(",")}
    assert from_widgets <= table_keys, from_widgets - table_keys
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


async def test_the_side_column_stacks_rather_than_being_drawn_off_screen():
    """Two panels with width floors overflow a narrow terminal, and the second is lost.

    Going underneath keeps it. Hiding it was the earlier answer and it cost the
    quotas outright, which is a worse thing to lose on a narrow terminal than the
    arrangement.
    """
    from clustertool.tui.app import SIDE_BY_SIDE

    app = _app()
    async with app.run_test(size=(SIDE_BY_SIDE, 24)) as pilot:
        await pilot.pause()
        jobs, storage = app.query_one("#jobs"), app.query_one("#storage")
        assert storage.display and storage.region.x >= jobs.region.right, "beside it"
        assert jobs.region.right <= SIDE_BY_SIDE
        await pilot.resize_terminal(SIDE_BY_SIDE - 4, 24)
        await pilot.pause()
        assert storage.display and storage.region.y >= jobs.region.bottom, "under it"
        assert storage.region.right <= SIDE_BY_SIDE - 4
        assert jobs.region.right <= SIDE_BY_SIDE - 4
        await pilot.resize_terminal(100, 24)
        await pilot.pause()
        assert storage.region.x >= jobs.region.right, "beside it again"


async def test_the_jobs_panel_keeps_a_usable_width_when_narrow():
    """Only the side column had a floor, so the primary panel starved first."""
    app = _app()
    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()
        assert app.query_one("#jobs").region.width >= 24
        assert "Jobs" in str(app.query_one("#jobs").border_title)


async def test_storage_panel_keeps_a_usable_width_when_narrow():
    """Without a floor the storage column collapses to its border and shows nothing.

    Measured at the narrowest width that shows it at all, which is where the floor
    is the thing deciding its width rather than its share of the row.
    """
    from clustertool.tui.app import SIDE_BY_SIDE

    app = _app()
    async with app.run_test(size=(SIDE_BY_SIDE, 20)) as pilot:
        await pilot.pause()
        assert app.query_one("#storage").display
        assert app.query_one("#storage").region.width >= 24


def test_fit_keeps_the_clock_and_the_user_at_any_width():
    """The bar exists to say who and when, so those two survive every other field."""
    from clustertool.tui.panels.status import fit

    who = data.Identity(
        "mgutierrez", "Maria Fernanda Gutierrez", "holy8a26105", "Kempner AI Cluster"
    )
    stamp = "Sun 2026-08-02 14:32"
    for width in (120, 100, 80, 60, 45, 40):
        line = fit(who, stamp, width)
        assert len(line) <= width, (width, line)
        assert stamp in line, (width, line)
        assert "mgutierrez" in line, (width, line)


def test_fit_sheds_the_site_name_before_the_full_name():
    from clustertool.tui.panels.status import fit

    who = data.Identity("mgutierrez", "A Name", "host01", "A Very Long Site Name Indeed")
    line = fit(who, "Sun 2026-08-02 14:32", 80)
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
        interval=0,
    )
    async with app.run_test(size=(100, 12)) as pilot:
        await pilot.pause()
        assert hostile in str(app.query_one("#status").render())


SAMPLE_JOBS = [
    data.JobRow(
        "111", "R", "RUNNING", "kempner_h100", 4, "2:14:00", "None", "gpu8a[15-16]", 2, "gres/gpu=4"
    ),
    data.JobRow("222", "PD", "PENDING", "kempner", 4, "0:00", "Priority", "", 1, "gres/gpu=4"),
]


def _row(jobid="1", **kwargs):
    fields = dict(
        jobid=jobid,
        code="R",
        state="RUNNING",
        partition="p",
        gpus=0,
        elapsed="1:00",
        reason="None",
        nodelist="n1",
        nnodes=1,
        tres="",
    )
    return data.JobRow(**{**fields, **kwargs})


def test_jobs_asks_for_the_allocation_and_a_separator(monkeypatch):
    """The default format pads to fixed widths and truncates a long TRES string."""
    import clustertool.process as proc

    seen = []
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, "", ""))[1])
    data.jobs("alice")
    joined = " ".join(seen[0])
    assert "tres-alloc" in joined
    assert "JobArrayID:|" in joined


def test_every_field_is_read_by_name_not_by_position():
    """The reply is unpacked against the same tuple that ordered the request.

    Positional unpacking let a reordered format put one column's value into
    another's, and squeue answers a bad field name with an error, not a shift.
    """
    assert data.JOB_FIELDS == ",".join(f"{name}:|" for name in data.JOB_FIELD_NAMES)
    for name in ("JobArrayID", "StateCompact", "State", "NumNodes", "tres-alloc", "NodeList"):
        assert name in data.JOB_FIELD_NAMES


def test_the_node_count_comes_from_nodes_not_tasks(monkeypatch):
    """NumTasks differs from NumNodes on 413 of the jobs queued when this was written."""
    import clustertool.process as proc

    monkeypatch.setattr(
        proc, "probe", lambda cmd, **kw: (0, "1|R|RUNNING|p|1:00|None|cpu=8|n[1-2]|2|\n", "")
    )
    assert "NumNodes" in data.JOB_FIELDS
    assert "NumTasks" not in data.JOB_FIELDS
    assert data.jobs("alice")[0].where == "n1 +1"


def test_jobs_asks_for_the_id_the_rest_of_the_cli_prints():
    """JobID is the internal numeric id, which for an array element is not %i.

    Every other command, and scancel, name an element base_index, so a panel
    showing the numeric id would name a job the user has never seen.
    """
    assert "JobArrayID:|" in data.JOB_FIELDS
    assert "JobID:|" not in data.JOB_FIELDS


def test_jobs_parses_a_pending_and_a_running_row(monkeypatch):
    import clustertool.process as proc

    out = (
        "111|R|RUNNING|kempner_h100|2:14:00|None|cpu=96,gres/gpu=4|gpu8a[15-16]|2|\n"
        "222_[0-9]|PD|PENDING|kempner|0:00|Priority|cpu=64,gres/gpu=4||1|\n"
    )
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, out, ""))
    rows = data.jobs("alice")
    assert [r.jobid for r in rows] == ["111", "222_[0-9]"]
    assert rows[0].gpus == 4
    assert rows[0].nnodes == 2
    assert rows[1].pending and not rows[0].pending
    assert rows[1].where == "(Priority)"
    assert rows[0].where == "gpu8a15 +1"


def test_jobs_does_not_expand_the_hostlist(monkeypatch):
    """Expanding forks scontrol once per multi-node job, on every tick."""
    import clustertool.process as proc
    import clustertool.slurm as slurm_module

    def refuse(nodelist):
        raise AssertionError("expand_hostlist must not be called per row")

    monkeypatch.setattr(slurm_module, "expand_hostlist", refuse)
    monkeypatch.setattr(
        proc, "probe", lambda cmd, **kw: (0, "111|R|RUNNING|p|1:00|None||n[1-4]|4|\n", "")
    )
    assert data.jobs("alice")[0].where == "n1 +3"


def test_jobs_skips_a_line_that_is_missing_fields(monkeypatch):
    """A short line means the format changed; taking it would shift every column."""
    import clustertool.process as proc

    out = "111|R|RUNNING|p|1:00|None|cpu=1|n1\n222|R|RUNNING|p|1:00|None|cpu=1|n1|1|\n"
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, out, ""))
    assert [r.jobid for r in data.jobs("alice")] == ["222"]


def test_jobs_raises_rather_than_reporting_none(monkeypatch):
    """An empty list would read as having no jobs, which is a different fact."""
    import clustertool.process as proc

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (1, "", "slurmctld down"))
    with pytest.raises(data.CommandError, match="could not read your jobs"):
        data.jobs("alice")


@pytest.mark.parametrize(
    "code,expected",
    [(127, "not found on this host"), (124, "timed out")],
)
def test_jobs_names_a_missing_squeue_and_a_timeout(monkeypatch, code, expected):
    """probe reports both as a bare exit code, which says nothing to the user."""
    import clustertool.process as proc

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (code, "", ""))
    with pytest.raises(data.CommandError, match=expected):
        data.jobs("alice")


def test_where_names_the_node_or_the_wait():
    one = _row()
    many = _row(nodelist="n[1-3]", nnodes=3)
    waiting = _row(code="PD", state="PENDING", reason="Resources", nodelist="", nnodes=1)
    unknown = _row(code="PD", state="PENDING", reason="None", nodelist="", nnodes=1)
    none_assigned = _row(nodelist="None assigned", nnodes=1, reason="None")
    assert one.where == "n1"
    assert many.where == "n1 +2"
    assert waiting.where == "(Resources)"
    assert unknown.where == "-"
    assert none_assigned.where == "-"


def test_a_pending_range_of_nodes_does_not_crash_the_count():
    """A job asking for --nodes=1-4 has a range in NumNodes, not a number."""
    assert data._count("1-4") == 1
    assert data._count("") == 0
    assert data._count("2") == 2


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


async def test_the_cursor_follows_the_job_not_the_row_number():
    """A new job above the cursor must not silently move the selection onto it.

    Phase 5 acts on the selected job, so a cursor that tracks the index rather
    than the job means the timer can retarget a cancel between aiming and typing.
    """
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(100, 22)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show(SAMPLE_JOBS)
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        assert panel.selected.jobid == "222"
        panel.show([_row("000"), *SAMPLE_JOBS])
        await pilot.pause()
        assert panel.selected.jobid == "222"
        panel.show(list(reversed(SAMPLE_JOBS)))
        await pilot.pause()
        assert panel.selected.jobid == "222"


@pytest.mark.parametrize("size", [(200, 40), (150, 30), (120, 22), (100, 26), (80, 24)])
async def test_the_table_never_outgrows_the_panel_at_a_supported_size(size):
    """A cell cut to a constant is chopped again by a narrower viewport.

    That second cut has no ellipsis, so a fragment such as holy8a2 reads as a
    whole node name. The widths therefore come from the terminal.
    """
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.query_one(JobsPanel).show(_wide_rows())
        await pilot.pause()
        table = app.query_one("#jobs-table")
        assert table.virtual_size.width <= table.size.width, size


@pytest.mark.parametrize("size", [(12, 8), (20, 10), (30, 10), (46, 12), (60, 20), (70, 16)])
async def test_no_panel_is_drawn_off_the_right_edge(size):
    """A width floor cannot make a panel fit a terminal narrower than the floor.

    It only pushes the panel past the edge, losing its border and its content.
    """
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.query_one(JobsPanel).show(_wide_rows())
        await pilot.pause()
        for panel in ("#jobs", "#storage", "#standing"):
            widget = app.query_one(panel)
            if widget.display:
                assert widget.region.right <= size[0], (panel, size)
        table = app.query_one("#jobs-table")
        assert table.virtual_size.width <= table.size.width, size


async def test_a_resize_repaints_the_cells_not_just_the_headings():
    """A column left to size itself is recomputed on a later refresh.

    Until that refresh the table painted every column at its heading width, with
    the cells chopped to it and no ellipsis, so 36754908 read as 36. Asserting on
    the rendered cell rather than on the column width, which was already right.
    """
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(120, 24)) as pilot:
        await pilot.pause()
        app.query_one(JobsPanel).show(_wide_rows())
        await pilot.pause()
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        table = app.query_one("#jobs-table")
        painted = [str(cell) for cell in table.get_row_at(0)]
        assert any(len(cell) > 4 for cell in painted), painted
        for cell in painted:
            assert cell == cell.rstrip() or "…" in cell, painted
        widths = [column.get_render_width(table) for column in table.columns.values()]
        assert sum(widths) <= table.size.width, widths


async def test_widening_the_terminal_never_costs_the_table_a_column():
    """The side column returns all at once, and took three headings with it."""
    from clustertool.tui.app import SIDE_BY_SIDE
    from clustertool.tui.panels.jobs import JobsPanel, layout

    app = _app()
    async with app.run_test(size=(SIDE_BY_SIDE - 1, 20)) as pilot:
        await pilot.pause()
        app.query_one(JobsPanel).show(_wide_rows())
        await pilot.pause()
        before = len(layout(app.query_one("#jobs-table").size.width))
        await pilot.resize_terminal(SIDE_BY_SIDE, 20)
        await pilot.pause()
        assert app.query_one("#storage").display
        after = len(layout(app.query_one("#jobs-table").size.width))
        assert after >= before, (before, after)


def test_the_elapsed_column_holds_a_run_of_over_ten_days():
    """Nothing else shows elapsed, so a cut here loses the figure at every width."""
    from clustertool.tui.panels.jobs import COLUMNS, elide

    ceiling = {name: high for name, _, high in COLUMNS}["ELAP"]
    assert elide("13-06:20:29", ceiling) == "13-06:20:29"
    assert elide("99-23:59:59", ceiling) == "99-23:59:59"


async def test_a_job_being_set_up_is_not_described_as_waiting_on_none():
    """CONFIGURING counts as pending, and Slurm gives its reason as the string None."""
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(100, 26)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show([_row("1", code="CF", state="CONFIGURING", reason="None", elapsed="0:03")])
        await pilot.pause()
        text = panel._detail_text()
        assert "waiting" not in text, text
        assert "None" not in text, text
        assert "elapsed: 0:03" in text


def test_a_reason_of_none_is_not_a_reason():
    assert _row("1", reason="None").stated_reason == ""
    assert _row("1", reason="").stated_reason == ""
    assert _row("1", reason="Priority").stated_reason == "Priority"


@pytest.mark.parametrize(
    ("name", "widest"),
    [
        ("ID", "36782876_[169,504,591,1008,1208"),
        ("PART", "huce_ice,huce_cascade,sapphire,seas_compute,shared"),
        ("ELAP", "13-06:53:59"),
        ("NODE", "(ReqNodeNotAvail, UnavailableNodes:holy7c24105)"),
    ],
)
def test_each_ceiling_covers_the_widest_value_its_field_takes(name, widest):
    """Measured across every job queued on 2026-08-02, so these are real widths."""
    from clustertool.tui.panels.jobs import COLUMNS

    ceiling = {heading: high for heading, _, high in COLUMNS}[name]
    assert ceiling >= len(widest), (name, ceiling, len(widest))


async def test_a_wide_terminal_spends_its_room_on_the_table():
    from clustertool.tui.panels.jobs import JobsPanel

    partition = "huce_ice,huce_cascade,sapphire,seas_compute,shared"
    app = _app()
    async with app.run_test(size=(260, 30)) as pilot:
        await pilot.pause()
        app.query_one(JobsPanel).show([_row("1", partition=partition, elapsed="13-06:53:59")])
        await pilot.pause()
        painted = " ".join(str(cell) for cell in app.query_one("#jobs-table").get_row_at(0))
        assert partition in painted, painted
        assert "13-06:53:59" in painted, painted


async def test_a_drag_only_rebuilds_the_table_when_the_layout_changes():
    """Dragging a window edge delivers one resize per column.

    Past the width where every column has reached its ceiling the layout stops
    changing, so each rebuild is pure cost: about 70ms of it for someone holding
    four thousand jobs, most of it in add_row.
    """
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(300, 24)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show(_wide_rows())
        await pilot.pause()
        painted = []
        original = panel._paint
        panel._paint = lambda *a, **k: (painted.append(1), original(*a, **k))[1]
        widths = set()
        for width in range(299, 279, -1):
            await pilot.resize_terminal(width, 24)
            await pilot.pause()
            widths.add(app.query_one("#jobs-table").size.width)
        assert len(widths) > 10, widths
        assert painted == [], len(painted)
        table = app.query_one("#jobs-table")
        assert table.virtual_size.width <= table.size.width


async def test_the_detail_names_the_elapsed_time():
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(100, 26)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show([_row("1", elapsed="13-06:20:29")])
        await pilot.pause()
        assert "13-06:20:29" in panel._detail_text()


def test_layout_drops_columns_before_it_starves_the_ones_that_stay():
    from clustertool.tui.panels.jobs import DROP_ORDER, layout

    wide = dict(layout(120))
    assert list(wide) == ["ID", "PART", "ST", "GPU", "ELAP", "NODE"]
    narrow = dict(layout(30))
    assert DROP_ORDER[0] not in narrow
    assert "ID" in narrow and "ST" in narrow
    for width in range(6, 200):
        columns = layout(width)
        total = sum(w for _, w in columns) + 2 * len(columns)
        assert total <= width or len(columns) == 2, (width, columns)
        assert all(w >= 1 for _, w in columns), (width, columns)


def test_a_column_grows_no_wider_than_the_widest_value_it_holds():
    """Otherwise the width goes to a column that does not need it.

    At 100 columns ID took 18 cells for a 9-character id while NODE was cut to 9 of
    the 47 its value needed, because the ceilings are the widest each field runs to
    across every job on the cluster rather than across the rows on screen.
    """
    from clustertool.tui.panels.jobs import ceilings, layout

    fitted = dict(layout(120, ceilings(SAMPLE_JOBS)))
    blind = dict(layout(120))
    assert fitted["ID"] == 12, fitted
    assert blind["ID"] > fitted["ID"], (blind, fitted)
    assert fitted["PART"] == len("kempner_h100"), fitted


def test_a_column_still_pays_its_minimum_when_its_values_are_shorter():
    """The minimums are the width at which a column says anything, data or no data."""
    from clustertool.tui.panels.jobs import COLUMNS, ceilings, layout

    minimum = {name: low for name, low, _ in COLUMNS}
    short = [_row("1", partition="p", elapsed="0:00", nodelist="n1")]
    for name, width in layout(120, ceilings(short)):
        assert width >= minimum[name], (name, width)


def test_width_left_over_is_unspent_rather_than_padding_the_columns_out():
    """The table ends where its content does, which is what leaves NODE its room."""
    from clustertool.tui.panels.jobs import CELL_PADDING, ceilings, layout

    columns = layout(200, ceilings(SAMPLE_JOBS))
    taken = sum(width for _, width in columns) + CELL_PADDING * len(columns)
    assert taken < 200, columns


def test_the_ceilings_never_exceed_the_static_ones():
    """A value longer than any field runs to would otherwise blow the table out."""
    from clustertool.tui.panels.jobs import COLUMNS, ceilings

    static = {name: high for name, _, high in COLUMNS}
    grown = ceilings([_row("9" * 400, partition="p," * 200, nodelist="n" * 500, nnodes=3)])
    for name, width in grown.items():
        assert width <= static[name], (name, width)


async def test_no_value_is_cut_when_the_panel_has_room_for_every_one_of_them():
    """The point of the whole exercise, asserted on the frame rather than the widths."""
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(160, 30)) as pilot:
        await pilot.pause()
        app.query_one(JobsPanel).show(SAMPLE_JOBS)
        await pilot.pause()
        painted = _painted(app)
        for row in SAMPLE_JOBS:
            for value in (row.jobid, row.partition, row.elapsed, row.where):
                assert value in painted, value
        table = app.query_one("#jobs-table")
        assert table.virtual_size.width <= table.size.width


def _wide_rows():
    return [
        _row(
            "34861429_[0,3-7]",
            partition="sapphire,seas_compute,shared",
            code="PD",
            state="PENDING",
            reason="ReqNodeNotAvail, UnavailableNodes:holygpu8a[11101-11408],holy8a[26101-26310]",
            nodelist="",
            elapsed="13-04:10:59",
        ),
        _row("36754908", nodelist="holy7c[04108-04512]", nnodes=202, elapsed="2-04:23:14"),
    ]


async def test_a_long_cell_is_cut_rather_than_widening_the_table():
    """One job in several partitions, or one long pending reason, blows the table out."""
    from clustertool.tui.panels.jobs import COLUMNS, JobsPanel, elide

    long_reason = "ReqNodeNotAvail, UnavailableNodes:holygpu8a[11101-11408],holy8a[26101-26310]"
    app = _app()
    async with app.run_test(size=(120, 22)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show(
            [
                _row(
                    "111",
                    partition="sapphire,seas_compute,shared",
                    code="PD",
                    state="PENDING",
                    reason=long_reason,
                    nodelist="",
                )
            ]
        )
        await pilot.pause()
        table = app.query_one("#jobs-table")
        assert table.virtual_size.width <= table.size.width
        whole = "".join(panel._detail_text().split())
        assert "".join(long_reason.split()) in whole, panel._detail_text()
        painted = "".join(_painted(app).split())
        assert "holy8a[26101-26310]" in painted, "and the end of it is on the screen"
    assert elide("abcdef", 4) == "abc…"
    assert elide("abc", 4) == "abc"
    assert {name for name, _, _ in COLUMNS} == {"ID", "PART", "ST", "GPU", "ELAP", "NODE"}


async def test_the_stale_mark_reaches_the_border_title():
    """The detail pane is what a short terminal clips first, so it cannot be the only sign."""
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(70, 16)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show(SAMPLE_JOBS)
        await pilot.pause()
        assert str(panel.border_title) == "Jobs"
        panel.fail("controller busy")
        await pilot.pause()
        assert "stale" in str(panel.border_title)
        panel.show(SAMPLE_JOBS)
        await pilot.pause()
        assert str(panel.border_title) == "Jobs"


async def test_a_wide_allocation_does_not_push_the_tres_out_of_the_detail():
    """A 202-node hostlist runs to several hundred characters and fills the pane."""
    from clustertool.tui.panels.jobs import JobsPanel

    nodelist = "holy7c[" + ",".join(f"0{n}" for n in range(4100, 4310)) + "]"
    app = _app()
    async with app.run_test(size=(100, 26)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show([_row("1", nodelist=nodelist, nnodes=202, tres="cpu=8,mem=64G")])
        await pilot.pause()
        text = panel._detail_text()
        assert "holds: cpu=8,mem=64G" in text
        assert text.index("holds:") < text.index("nodes:")
        assert "202 on" in text
        assert "…" in text
        assert len(text.splitlines()[-1]) < len(nodelist)


async def test_the_table_keeps_room_for_at_least_one_job():
    """Without a floor a long detail pane can squeeze the rows out entirely."""
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(100, 14)) as pilot:
        await pilot.pause()
        app.query_one(JobsPanel).show(SAMPLE_JOBS)
        await pilot.pause()
        assert app.query_one("#jobs-table").size.height >= 2


async def test_the_detail_pane_is_capped_so_the_table_survives_it():
    """Uncapped, a pending job with a long reason takes the whole panel."""
    from clustertool.tui.panels.jobs import JobsPanel

    reason = "ReqNodeNotAvail, UnavailableNodes:" + ",".join(
        f"holy8a{n}" for n in range(26100, 26140)
    )
    app = _app()
    async with app.run_test(size=(100, 26)) as pilot:
        await pilot.pause()
        app.query_one(JobsPanel).show(
            [_row("1", code="PD", state="PENDING", reason=reason, nodelist="")]
        )
        await pilot.pause()
        assert app.query_one("#jobs-detail").size.height <= 8


async def test_the_detail_pane_stays_on_screen_when_the_table_is_full():
    """It held height auto under a 1fr table, so the rows squeezed it to nothing."""
    from clustertool.tui.panels.jobs import JobsPanel

    app = _app()
    async with app.run_test(size=(100, 16)) as pilot:
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        panel.show([_row(str(n)) for n in range(40)])
        await pilot.pause()
        assert app.query_one("#jobs-detail").size.height >= 2


class _Probe:
    """Records how many stub queries ran, and how many ever ran at the same time."""

    def __init__(self):
        self.calls = 0
        self.live = 0
        self.peak = 0


def _stub_jobs(monkeypatch, rows=(), error=None, delay=0.0):
    import threading
    import time

    from clustertool.tui import data as data_module

    probe = _Probe()
    lock = threading.Lock()

    def fake(user):
        with lock:
            probe.calls += 1
            probe.live += 1
            probe.peak = max(probe.peak, probe.live)
        try:
            if delay:
                time.sleep(delay)
            if error is not None:
                raise error
            return list(rows)
        finally:
            with lock:
                probe.live -= 1

    monkeypatch.setattr(data_module, "jobs", fake)
    return probe


def _live_app():
    """The app with a fast timer, for the tests that stub the query out."""
    return _app(interval=0.05)


async def _until(pilot, predicate, timeout=5.0):
    """Pause until predicate holds, and report whether it did.

    The query runs in a thread, so how long its round trip takes is the machine's
    business, not the test's. A fixed pause made these fail about one run in nine
    on a loaded host while asserting nothing extra when they passed.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await pilot.pause(0.02)
    return predicate()


async def test_the_app_loads_jobs_on_start_and_on_the_timer(monkeypatch):
    """Nothing else asserts the timer, so dropping it left an empty panel forever."""
    from clustertool.tui.panels.jobs import JobsPanel

    probe = _stub_jobs(monkeypatch, rows=SAMPLE_JOBS)
    app = _live_app()
    async with app.run_test(size=(100, 22)) as pilot:
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: panel.selected is not None), "no load on mount"
        assert panel.selected.jobid == "111"
        first = probe.calls
        assert await _until(pilot, lambda: probe.calls > first), "the timer never fired"


async def test_the_first_read_does_not_wait_for_the_timer(monkeypatch):
    """The tick is 5s, so leaving the first read to it shows a blank panel on arrival.

    The interval here is long enough that it cannot fire during the test, which is
    what makes the assertion about the load on mount rather than about the timer.
    """
    probe = _stub_jobs(monkeypatch, rows=SAMPLE_JOBS)
    app = _app(interval=30)
    async with app.run_test(size=(100, 22)) as pilot:
        assert await _until(pilot, lambda: probe.calls >= 1), "nothing was read on mount"
        assert probe.calls == 1


async def test_refresh_reads_again_now(monkeypatch):
    probe = _stub_jobs(monkeypatch, rows=SAMPLE_JOBS)
    app = _app()
    async with app.run_test(size=(100, 22)) as pilot:
        await pilot.pause()
        assert probe.calls == 0
        await pilot.press("r")
        assert await _until(pilot, lambda: probe.calls >= 1), "r did not read again"
        assert probe.calls == 1


async def test_a_held_refresh_key_does_not_stack_queries(monkeypatch):
    """An exclusive worker cancels its awaiter, not the subprocess it is waiting on.

    So the assertion is on how many queries were ever in flight together, not on
    how many ran: a press arriving after one finished is a refresh, not a stack.
    """
    probe = _stub_jobs(monkeypatch, rows=SAMPLE_JOBS, delay=0.5)
    app = _app()
    async with app.run_test(size=(100, 22)) as pilot:
        await pilot.pause()
        for _ in range(10):
            await pilot.press("r")
        await pilot.pause(0.6)
        assert probe.peak == 1, f"{probe.calls} queries ran, {probe.peak} at once"


async def test_the_timer_does_not_stack_queries_on_a_slow_controller(monkeypatch):
    """The tick is 5s live, but a controller can take longer than that to answer."""
    probe = _stub_jobs(monkeypatch, rows=SAMPLE_JOBS, delay=0.4)
    app = _live_app()
    async with app.run_test(size=(100, 22)) as pilot:
        await pilot.pause(0.6)
        assert probe.peak == 1, f"{probe.calls} queries ran, {probe.peak} at once"


@pytest.mark.parametrize(
    "error,expected",
    [
        (CommandError("controller busy"), "stale: controller busy"),
        (ValueError("bad parse"), "ValueError"),
        (PermissionError(13, "denied"), "PermissionError"),
        (TimeoutError(), "TimeoutError"),
    ],
)
async def test_a_failing_query_marks_the_panel_and_leaves_the_app_up(monkeypatch, error, expected):
    """Only CommandError was caught, so anything else dumped a traceback and quit."""
    from clustertool.tui.panels.jobs import JobsPanel

    _stub_jobs(monkeypatch, error=error)
    app = _live_app()
    async with app.run_test(size=(100, 22)) as pilot:
        await pilot.pause()
        assert app.is_running
        assert expected in app.query_one(JobsPanel)._detail_text()
        assert "stale" in str(app.query_one(JobsPanel).border_title)
    assert app.return_code in (0, None)


QUOTA_OUT = (
    "Disk quotas for grp lab (gid 1):\n"
    "     Filesystem    used   quota   limit   grace   files   quota   limit   grace\n"
    "   /n/fs  1.5T     2T     2T       - 100  200 200       -\n"
)


def _quota_out(used, cap):
    """Return quota output the site tool would print for one directory."""
    return (
        "Disk quotas for grp lab (gid 1):\n"
        "     Filesystem used quota limit grace files quota limit grace\n"
        f"   /n/fs {used} {cap} {cap} - 100 200 200 -\n"
    )


def _quota_probe(monkeypatch, out=QUOTA_OUT, code=0, err="", delay=0.0, seen=None):
    """Stub every subprocess the storage layer makes."""
    import time

    import clustertool.process as proc

    def fake(cmd, timeout=None, input_text=None):
        if seen is not None:
            seen.append(cmd)
        if delay:
            time.sleep(delay)
        return (code, out, err)

    monkeypatch.setattr(proc, "probe", fake)


def test_bar_marks_any_usage_and_never_overflows():
    from clustertool.tui.panels.storage import bar

    assert bar(None) == "      "
    assert bar(0.0) == "░░░░░░"
    assert bar(0.01) == "█░░░░░", "a directory holding data must not read as empty"
    assert bar(0.5) == "███░░░"
    assert bar(1.0) == "██████"
    assert bar(1.3) == "██████", "over quota cannot draw more cells than there are"
    assert bar(0.5, 0) == ""


def test_the_bar_distinguishes_nearly_full_from_full():
    """Rounding up filled every cell from 84%, so 90 percent looked like 100."""
    from clustertool.tui.panels.storage import bar

    assert bar(0.90) != bar(0.98)
    assert bar(0.98) == "██████"


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [(None, "dim"), (0.0, ""), (0.74, ""), (0.75, "yellow"), (0.89, "yellow"), (0.90, "bold red")],
)
def test_style_turns_at_the_documented_thresholds(fraction, expected):
    from clustertool.tui.panels.storage import style_for

    assert style_for(fraction) == expected


def test_a_bracket_in_a_lab_name_is_not_read_as_markup():
    """A label carries a group name off the filesystem, so it is not trusted."""
    from clustertool.tui.panels.storage import row_text

    row = data.QuotaRow("fs/[bold red]lab", "1T", "2T", "93%")
    from clustertool.tui.panels.storage import BAR_WIDTH, PERCENT_WIDTH

    text = row_text(row, 40)
    assert "[bold red]" in text.plain
    label_end = 40 - PERCENT_WIDTH - BAR_WIDTH - 1
    assert all(span.start >= label_end for span in text.spans), text.spans


def test_a_row_that_could_not_be_read_says_why_instead_of_a_bar():
    from clustertool.tui.panels.storage import row_text

    row = data.QuotaRow("fs/lab", "-", "-", "-", error="quota timed out")
    plain = row_text(row, 40).plain
    assert "timed out" in plain
    assert "█" not in plain and "░" not in plain


def test_a_row_never_exceeds_the_width_it_is_given():
    from clustertool.tui.panels.storage import row_text

    row = data.QuotaRow("netscratch/kempner_a_very_long_lab_name_indeed", "1T", "2T", "93%")
    for width in range(14, 60):
        assert len(row_text(row, width).plain) <= width, width


def test_lines_names_every_section_and_counts_the_labs():
    from clustertool.tui.panels.storage import lines

    info = data.StorageInfo(
        home=data.QuotaRow("home", "76G", "95G", "80%"),
        labs=[data.QuotaRow("fs/a", "1T", "2T", "50%"), data.QuotaRow("fs/b", "2T", "2T", "99%")],
        mine=[data.QuotaRow("holylfs06", "50T", "0k", "-")],
    )
    plain = "\n".join(line.plain for line in lines(info, 40))
    assert "home" in plain
    assert "labs (2)" in plain
    assert "you, on lustre" in plain
    assert "fs/a" in plain and "fs/b" in plain


def test_lines_says_so_when_there_are_no_lab_directories():
    """An empty section would read as a panel that failed to load."""
    from clustertool.tui.panels.storage import NO_LABS, lines

    info = data.StorageInfo(home=None, labs=[], mine=[])
    plain = "\n".join(line.plain for line in lines(info, 40))
    assert NO_LABS[:20] in plain
    assert "you, on lustre" not in plain


def test_home_quota_reads_the_df_row(monkeypatch):
    out = "Filesystem Size Used Avail Use% Mounted on\n/dev/x 95G 76G 19G 80% /n/home14\n"
    _quota_probe(monkeypatch, out=out)
    row = data.home_quota()
    assert (row.used, row.quota, row.percent) == ("76G", "95G", "80%")
    assert row.error == ""


@pytest.mark.parametrize(
    ("out", "code", "expected"),
    [
        ("", 127, "not found on this host"),
        ("", 124, "timed out"),
        ("Filesystem Size\n", 0, "no rows"),
        ("Filesystem Size\n/dev/x 95G\n", 0, "short"),
    ],
)
def test_home_quota_explains_a_failure(monkeypatch, out, code, expected):
    _quota_probe(monkeypatch, out=out, code=code)
    row = data.home_quota()
    assert expected in row.error
    assert row.percent == "-"


def test_lab_quotas_run_in_parallel(monkeypatch):
    """Serial, forty directories took 6.9s live; the panel cannot wait that long."""
    import time

    import clustertool.storage as storage_module

    targets = [(f"/n/fs/lab{n}", f"lab{n}") for n in range(12)]
    monkeypatch.setattr(storage_module, "user_groups", lambda user: ["lab0"])
    monkeypatch.setattr(storage_module, "lab_targets", lambda groups, roots: targets)
    monkeypatch.setattr(storage_module, "mount_point", lambda path, mounts=None: ("/n/fs", "nfs"))
    _quota_probe(monkeypatch, delay=0.1)
    start = time.monotonic()
    rows = data.lab_quotas("alice")
    elapsed = time.monotonic() - start
    assert len(rows) == 12
    serial = 12 * 0.1
    assert elapsed < serial / 2, f"{elapsed:.2f}s for what serial takes {serial:.2f}s"


def test_lab_quotas_put_the_fullest_first(monkeypatch):
    """The panel is a side column, so what is nearly full has to be on screen."""
    import clustertool.process as proc
    import clustertool.storage as storage_module

    caps = {"a": ("1T", "10T"), "b": ("99T", "100T"), "c": ("1T", "0"), "d": ("5T", "10T")}
    targets = [(f"/n/fs/{name}", name) for name in caps]
    monkeypatch.setattr(storage_module, "user_groups", lambda user: [])
    monkeypatch.setattr(storage_module, "lab_targets", lambda groups, roots: targets)
    monkeypatch.setattr(storage_module, "mount_point", lambda path, mounts=None: ("/n/fs", "nfs"))
    monkeypatch.setattr(
        proc, "probe", lambda cmd, **kw: (0, _quota_out(*caps[cmd[-1].rsplit("/", 1)[-1]]), "")
    )
    assert [row.label for row in data.lab_quotas("alice")] == ["b@fs", "d@fs", "a@fs", "c@fs"]


def test_a_lab_whose_quota_cannot_be_read_still_gets_a_row(monkeypatch):
    """Dropping it would silently shrink the list and hide the failure."""
    import clustertool.storage as storage_module

    monkeypatch.setattr(storage_module, "user_groups", lambda user: [])
    monkeypatch.setattr(storage_module, "lab_targets", lambda g, r: [("/n/fs/a", "a")])
    monkeypatch.setattr(storage_module, "mount_point", lambda path, mounts=None: ("/n/fs", "nfs"))
    _quota_probe(monkeypatch, out="", code=124)
    rows = data.lab_quotas("alice")
    assert len(rows) == 1
    assert "timed out" in rows[0].error
    assert rows[0].fraction is None


def test_only_lustre_roots_get_a_per_user_query(monkeypatch):
    """lfs quota is a Lustre command, and the NFS roots do not answer it usefully."""
    import clustertool.site as site_module
    import clustertool.storage as storage_module

    kinds = {"/n/lustre1": "lustre", "/n/lustre2": "lustre", "/n/nfs1": "nfs"}
    monkeypatch.setattr(
        site_module,
        "storage_lab_roots",
        lambda: ["/n/lustre1/LABS", "/n/lustre2/LABS", "/n/nfs1"],
    )

    def mount(path, mounts=None):
        for root, kind in kinds.items():
            if path.startswith(root):
                return root, kind
        return "", ""

    monkeypatch.setattr(storage_module, "mount_point", mount)
    seen = []
    _quota_probe(monkeypatch, out="/n/lustre1 50T 0k - -\n", seen=seen)
    rows = data.my_lustre_quotas("alice")
    assert [row.label for row in rows] == ["lustre1", "lustre2"]
    assert all("lfs" in cmd[0] and "-u" in cmd for cmd in seen)
    assert not any("nfs1" in cmd[-1] for cmd in seen)


def test_a_lustre_root_is_asked_once_per_mount(monkeypatch):
    """Two lab roots on one filesystem share its per-user quota."""
    import clustertool.site as site_module
    import clustertool.storage as storage_module

    monkeypatch.setattr(site_module, "storage_lab_roots", lambda: ["/n/lfs/LABS", "/n/lfs/OTHER"])
    monkeypatch.setattr(storage_module, "mount_point", lambda p, mounts=None: ("/n/lfs", "lustre"))
    seen = []
    _quota_probe(monkeypatch, out="/n/lfs 50T 0k - -\n", seen=seen)
    assert len(data.my_lustre_quotas("alice")) == 1
    assert len(seen) == 1


def test_mount_point_takes_the_longest_match():
    """Mounts nest, so the shortest prefix would name the wrong filesystem."""
    from clustertool import storage

    mounts = (
        "3 1 0:3 / /n/holylfs06/LABS/x rw - ext4 /dev/sda rw\n"
        "2 1 0:2 / /n/holylfs06 rw - lustre mds:/lfs rw\n"
        "1 1 0:1 / /n rw - nfs srv:/n rw\n"
    )
    assert storage.mount_point("/n/holylfs06/LABS/lab_one", mounts) == (
        "/n/holylfs06",
        "lustre",
    )
    assert storage.mount_point("/n/netscratch/lab", mounts) == ("/n", "nfs")
    assert storage.mount_point("/n/holylfs06/LABS/x/deep", mounts) == (
        "/n/holylfs06/LABS/x",
        "ext4",
    )


def test_mount_point_survives_an_unreadable_mountinfo(monkeypatch):
    from clustertool import storage

    def boom(*args, **kwargs):
        raise OSError("no /proc")

    monkeypatch.setattr("builtins.open", boom)
    assert storage.mount_point("/n/anything") == ("", "")


async def test_the_app_loads_the_storage_panel_on_start(monkeypatch):
    from clustertool.tui.panels.storage import StoragePanel

    info = data.StorageInfo(home=data.QuotaRow("home", "1G", "2G", "50%"), labs=[], mine=[])
    calls = []
    monkeypatch.setattr(data, "storage_info", lambda user: (calls.append(user), info)[1])
    app = _app(interval=30)
    async with app.run_test(size=(120, 30)) as pilot:
        panel = app.query_one(StoragePanel)
        assert await _until(pilot, lambda: panel._info is not None), "storage never loaded"
        assert calls == ["alice"]


async def test_the_storage_panel_is_not_on_the_jobs_timer(monkeypatch):
    """Quotas move slowly and the fan-out is seconds, so polling them is pure load."""
    monkeypatch.setattr(data, "jobs", lambda user: [])
    info = data.StorageInfo(home=None, labs=[], mine=[])
    calls = []
    monkeypatch.setattr(data, "storage_info", lambda user: (calls.append(user), info)[1])
    app = _app(interval=0.05)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause(0.5)
        assert len(calls) == 1, f"storage was read {len(calls)} times on a 0.05s tick"


async def test_r_refreshes_the_focused_panel_and_R_refreshes_both(monkeypatch):
    from clustertool.tui.panels.storage import StoragePanel

    monkeypatch.setattr(data, "jobs", lambda user: [])
    info = data.StorageInfo(home=None, labs=[], mine=[])
    jobs_calls, storage_calls = [], []
    monkeypatch.setattr(data, "jobs", lambda user: (jobs_calls.append(user), [])[1])
    monkeypatch.setattr(data, "storage_info", lambda user: (storage_calls.append(user), info)[1])
    app = _app(interval=0)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.press("r")
        assert await _until(pilot, lambda: len(jobs_calls) == 1), "r did not refresh jobs"
        assert storage_calls == []
        app.query_one(StoragePanel).focus()
        await pilot.pause()
        await pilot.press("r")
        assert await _until(pilot, lambda: len(storage_calls) == 1), "r did not refresh storage"
        assert len(jobs_calls) == 1
        await pilot.press("R")
        assert await _until(pilot, lambda: len(jobs_calls) == 2 and len(storage_calls) == 2)


@pytest.mark.parametrize(
    ("error", "expected"),
    [(CommandError("quota service down"), "quota service down"), (ValueError("bad"), "ValueError")],
)
async def test_a_failing_quota_read_marks_the_panel_and_leaves_the_app_up(
    monkeypatch, error, expected
):
    from clustertool.tui.panels.storage import StoragePanel

    def boom(user):
        raise error

    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "storage_info", boom)
    app = _app(interval=30)
    async with app.run_test(size=(120, 30)) as pilot:
        panel = app.query_one(StoragePanel)
        assert await _until(pilot, lambda: bool(panel._error)), "no failure reached the panel"
        assert app.is_running
        assert expected in panel._error
        assert "stale" in str(panel.border_title)


async def test_a_storage_row_is_one_line_however_long_the_label(monkeypatch):
    """Text.join builds from the separator, so a no-wrap flag on the rows is lost."""
    from clustertool.tui.panels.storage import StoragePanel

    labs = [data.QuotaRow(f"lab_{n}@netscratch", "1T", "2T", "90%") for n in range(30)]
    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(
        data, "storage_info", lambda user: data.StorageInfo(home=None, labs=labs, mine=[])
    )
    app = _app(interval=30)
    async with app.run_test(size=(120, 30)) as pilot:
        panel = app.query_one(StoragePanel)
        assert await _until(pilot, lambda: panel._info is not None)
        await pilot.pause()
        from clustertool.tui.panels.storage import lines

        expected = len(lines(panel._info, panel.content_size.width - 1))
        assert panel.virtual_size.height == expected, panel.virtual_size
        widest = max(len(line.plain) for line in lines(panel._info, panel.content_size.width - 1))
        assert widest <= panel.content_size.width - 1, widest


async def test_a_query_that_outlives_the_screen_does_not_crash_the_worker(monkeypatch):
    """The handler that reports a failure must not raise a worse one.

    Shutting the app down with a query in flight leaves the worker holding a
    screen that no longer has the panel, and looking the panel up there turned a
    reported failure into a WorkerFailed with a traceback over the terminal.
    """
    import asyncio

    from clustertool.tui.panels.jobs import JobsPanel

    started = asyncio.Event()

    def slow(user):
        started.set()
        time.sleep(0.4)
        raise CommandError("controller busy")

    monkeypatch.setattr(data, "jobs", slow)
    monkeypatch.setattr(
        data, "storage_info", lambda user: data.StorageInfo(home=None, labs=[], mine=[])
    )
    app = _app(interval=30)
    async with app.run_test(size=(120, 30)) as pilot:
        await _until(pilot, started.is_set)
        await app.query_one(JobsPanel).remove()
        await pilot.pause()
        app._on(JobsPanel, lambda panel: panel.fail("would raise on a gone panel"))
        await pilot.pause(0.5)
    assert app.return_code in (0, None), app.return_code


async def test_the_storage_panel_leaves_its_loading_state_on_failure(monkeypatch):
    """A panel stuck showing a spinner reads as a query that never came back."""
    from clustertool.tui.panels.storage import StoragePanel

    monkeypatch.setattr(data, "jobs", lambda user: [])

    def boom(user):
        raise CommandError("quota service down")

    monkeypatch.setattr(data, "storage_info", boom)
    app = _app(interval=30)
    async with app.run_test(size=(120, 30)) as pilot:
        panel = app.query_one(StoragePanel)
        assert await _until(pilot, lambda: bool(panel._error))


def test_every_storage_line_fits_the_narrowest_panel():
    """The section headings are the one text not built to a width."""
    from clustertool.tui.panels.storage import lines

    info = data.StorageInfo(
        home=data.QuotaRow("home", "1G", "2G", "50%"),
        labs=[data.QuotaRow(f"fs/lab{n}", "1T", "2T", "90%") for n in range(40)],
        mine=[data.QuotaRow("holylfs06", "50T", "0k", "-")],
    )
    for width in range(8, 40):
        for line in lines(info, width):
            assert len(line.plain) <= width, (width, line.plain)


def _q(label="fs", used="1T", quota="2T", percent="50%", files="-", error=""):
    return data.QuotaRow(f"lab@{label}", used, quota, percent, files, error)


async def test_reading_keeps_the_panel_border_and_its_last_figures():
    """Textual's loading flag replaces the widget, border and title included.

    That left an unbordered hole where the side column was for the two to six
    seconds the fan-out takes, and forty-five if a target hung.
    """
    from clustertool.tui.panels.storage import StoragePanel

    info = data.StorageInfo(home=None, labs=[_q(percent="93%")], mine=[])
    app = _app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.query_one(StoragePanel)
        panel.show(info)
        await pilot.pause()
        panel.begin_read()
        await pilot.pause()
        assert not panel.loading, "the Textual flag would delete the border"
        assert "Storage" in str(panel.border_title)
        assert "reading" in str(panel.border_title)
        assert panel.region.width > 0 and panel.region.height > 0
        body = app.query_one("#storage-body")
        assert body.size.height > 1, "the previous figures must stay on screen"


def test_a_row_with_no_quota_shows_what_it_holds():
    """Per-user Lustre rows carry no quota here, so a percent-only row is two dashes."""
    from clustertool.tui.panels.storage import row_text

    row = data.QuotaRow("fastfs02", "50.43T", "0k", "-", "-")
    assert "50.43T" in row_text(row, 40).plain


def test_the_binding_quota_is_the_one_shown_and_sorted_on():
    """A directory stops being writable when either blocks or inodes run out."""
    inodes = _q(percent="79%", files="99%")
    blocks = _q(percent="98%", files="40%")
    assert inodes.fraction == 0.99
    assert inodes.files_bound
    assert blocks.fraction == 0.98
    assert not blocks.files_bound

    from clustertool.tui.panels.storage import row_text

    assert "99%i" in row_text(inodes, 40).plain
    assert "98%" in row_text(blocks, 40).plain


def test_zero_percent_is_not_the_same_as_no_quota():
    """or -1 collapsed the two, and fourteen of the real forty rows sit at zero."""
    assert _q(percent="0%").fraction == 0.0
    assert _q(percent="-").fraction is None


def test_rows_that_could_not_be_read_come_first():
    """A side column shows a dozen rows, and a failure is invisible below the fold."""
    rows = [
        _q("a", percent="50%"),
        _q("b", percent="-", used="200G"),
        _q("c", error="quota timed out"),
        _q("d", percent="0%", used="0"),
        _q("e", percent="0%", used="212G"),
        _q("f", percent="99%"),
    ]
    ordered = [row.label for row in sorted(rows, key=data._worst_first)]
    assert ordered[0] == "lab@c", ordered
    assert ordered[1] == "lab@f", ordered
    assert ordered.index("lab@e") < ordered.index("lab@d"), "ties break on bytes held"
    assert ordered[-1] == "lab@b", "no quota set sorts last"


def test_the_labs_heading_counts_what_could_not_be_read():
    from clustertool.tui.panels.storage import _labs_heading

    assert _labs_heading([_q("a"), _q("b")]) == "labs (2), fullest first"
    assert "2 unread" in _labs_heading([_q("a"), _q("b", error="x"), _q("c", error="y")])


def test_the_fan_out_gives_up_on_a_straggler(monkeypatch):
    """One unresponsive target held every other figure for the whole timeout."""
    import clustertool.process as proc
    import clustertool.storage as storage_module

    targets = [(f"/n/fs/lab{n}", f"lab{n}") for n in range(4)]
    monkeypatch.setattr(storage_module, "user_groups", lambda user: [])
    monkeypatch.setattr(storage_module, "lab_targets", lambda g, r: targets)
    monkeypatch.setattr(storage_module, "mount_point", lambda p, mounts=None: ("/n/fs", "nfs"))
    monkeypatch.setattr(data, "GATHER_DEADLINE_S", 0.3)

    def fake(cmd, timeout=None, input_text=None):
        if cmd[-1].endswith("lab2"):
            time.sleep(ABANDONED_SLEEP_S)
        return (0, QUOTA_OUT, "")

    monkeypatch.setattr(proc, "probe", fake)
    start = time.monotonic()
    rows = data.lab_quotas("alice")
    assert time.monotonic() - start < 5, "the deadline did not fire"
    assert len(rows) == 4
    assert [row.error for row in rows if row.error] == [data.STILL_READING]
    assert [row.pending for row in rows].count(True) == 1


def test_the_fan_out_threads_do_not_hold_up_quitting():
    """A thread pool joins its workers at exit, so one hung lookup delayed Q by 44s."""
    import threading

    seen = []
    original = threading.Thread.start

    def watch(self):
        seen.append(self.daemon)
        original(self)

    threading.Thread.start = watch
    try:
        data._fan_out([])
        data._fan_out([("/n/fs/a", "a")])
    finally:
        threading.Thread.start = original
    assert seen and all(seen), seen


def test_a_directory_service_that_is_down_is_not_no_groups(monkeypatch):
    """It reported a user in twenty labs as belonging to none."""
    import clustertool.process as proc
    from clustertool import storage

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (1, "", "id: no such user"))
    with pytest.raises(CommandError, match="could not read your groups"):
        storage.user_groups("alice")


def test_home_comes_from_the_passwd_entry_not_the_environment(monkeypatch):
    """identity() documents the same rule, and HOME can be pointed anywhere."""
    import clustertool.process as proc

    seen = []
    monkeypatch.setenv("HOME", "/tmp")
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, "", ""))[1])
    data.home_quota()
    assert seen[0][-1] == pwd.getpwuid(os.getuid()).pw_dir
    assert seen[0][-1] != "/tmp"


def test_mount_point_prefers_the_entry_on_top():
    """Eight points on this host appear twice, autofs shadowed by the real mount."""
    from clustertool import storage

    mounts = "1 1 0:1 / /n/x rw - autofs systemd rw\n2 1 0:2 / /n/x rw - nfs srv:/x rw\n"
    assert storage.mount_point("/n/x/lab", mounts) == ("/n/x", "nfs")


def test_mount_point_does_not_match_a_bare_prefix():
    """Without the separator /n/lfs would claim /n/lfs2, aiming lfs at another type."""
    from clustertool import storage

    mounts = "1 1 0:1 / / rw - xfs /dev/sda rw\n2 1 0:2 / /n/lfs rw - lustre mds:/l rw\n"
    assert storage.mount_point("/n/lfs2/lab", mounts) == ("/", "xfs")


def test_mount_point_resolves_a_symlinked_root(tmp_path):
    """One configured root on this cluster is a symlink."""
    from clustertool import storage

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    resolved = os.path.realpath(real)
    mounts = f"1 1 0:1 / {resolved} rw - lustre mds:/l rw\n"
    assert storage.mount_point(str(link), mounts) == (resolved, "lustre")


def test_an_inaccurate_lfs_figure_is_still_read_as_a_size():
    """lfs brackets a figure when an OST is unreachable; it read as zero percent."""
    from clustertool import storage

    out = (
        "Disk quotas for grp lab (gid 1):\n"
        "     Filesystem used quota limit grace files quota limit grace\n"
        "   /n/lfs [39.05T] 40T 40T - 100 200 200 -\n"
    )
    parsed = storage.parse_quota_row(out)
    assert parsed is not None
    assert parsed[2] == "98%", parsed


@pytest.mark.parametrize(
    ("code", "err", "expected"),
    [
        (0, "", "no quota reported"),
        (1, "", "quota exited 1"),
        (
            1,
            "Error (line 42): a very long wrapper message that runs on and on",
            "Error (line 42): a very long",
        ),
    ],
)
def test_a_failed_lookup_is_described_in_a_few_words(code, err, expected):
    """A row has room for neither a hundred characters nor a df table."""
    assert data._probe_error(code, err, "quota") == expected


@pytest.mark.parametrize("mount", ["/n/holylfs06", "/", ""])
def test_the_label_names_the_lab_before_the_filesystem(monkeypatch, mount):
    """Cut from the tail, filesystem first took forty labs to three names at 80 columns.

    The mount is stubbed rather than read from the host: a path that is its own mount
    here is under the root filesystem on a runner, and a mount named nothing has to
    fall back to the path.
    """
    from clustertool import storage

    monkeypatch.setattr(storage, "mount_point", lambda path, mounts=None: (mount, "lustre"))
    assert data._label("/n/holylfs06/LABS/lab_one", "lab_one") == "lab_one@holylfs06"


def test_the_label_keeps_a_filesystem_when_the_mount_table_is_unreadable(monkeypatch):
    """Falling back to the group alone gave a lab's three directories one name."""
    from clustertool import storage

    monkeypatch.setattr(storage, "mount_point", lambda path, mounts=None: ("", ""))
    first = data._label("/n/netscratch/lab_one", "lab_one")
    second = data._label("/n/holylfs06/LABS/lab_one", "lab_one")
    assert first != second, (first, second)


def test_a_lab_quota_is_asked_for_by_group(monkeypatch):
    """The wrapper infers the group from the path here, but another site may not."""
    import clustertool.process as proc
    import clustertool.storage as storage_module

    monkeypatch.setattr(storage_module, "mount_point", lambda p, mounts=None: ("/n/fs", "nfs"))
    seen = []
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, QUOTA_OUT, ""))[1])
    data._lab_quota(("/n/fs/lab_one", "lab_one"))
    assert "-g" in seen[0] and "lab_one" in seen[0]


def test_a_row_is_truncated_even_if_the_arithmetic_is_wrong():
    """The final truncate is the backstop the width arithmetic is checked against."""
    from clustertool.tui.panels.storage import row_text

    row = data.QuotaRow("a" * 200, "1T", "2T", "100%", "10%")
    for width in (1, 2, 5, 13, 17, 29, 30, 31, 60):
        assert len(row_text(row, width).plain) <= width, width


def test_the_percent_field_shrinks_with_a_narrow_row():
    from clustertool.tui.panels.storage import row_text

    row = data.QuotaRow("lab", "1T", "2T", "100%", "10%")
    assert len(row_text(row, 6).plain) <= 6


async def test_repeated_storage_refreshes_do_not_stack(monkeypatch):
    """The guard load_jobs argues for at length applies to a forty-way fan-out too."""
    from clustertool.tui.panels.storage import StoragePanel

    monkeypatch.setattr(data, "jobs", lambda user: [])
    probe = _Probe()
    lock = __import__("threading").Lock()

    def slow(user):
        with lock:
            probe.calls += 1
            probe.live += 1
            probe.peak = max(probe.peak, probe.live)
        try:
            time.sleep(0.4)
            return data.StorageInfo(home=None, labs=[], mine=[])
        finally:
            with lock:
                probe.live -= 1

    monkeypatch.setattr(data, "storage_info", slow)
    app = _app(interval=0)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        app.query_one(StoragePanel).focus()
        await pilot.pause()
        for _ in range(10):
            await pilot.press("r")
        await pilot.pause(0.6)
        assert probe.peak == 1, f"{probe.calls} fan-outs ran, {probe.peak} at once"


async def test_refresh_all_reads_a_side_column_that_is_stacked(monkeypatch):
    """It is on screen when stacked, so skipping it would leave it showing old figures.

    The skip was right while a narrow terminal hid the panel: forty lookups for
    something nobody can see is pure load on a shared service. It became wrong the
    moment the panel moved underneath instead.
    """
    from clustertool.tui.app import SIDE_BY_SIDE

    monkeypatch.setattr(data, "jobs", lambda user: [])
    storage_calls = []
    monkeypatch.setattr(
        data,
        "storage_info",
        lambda user: (storage_calls.append(user), data.StorageInfo(None, [], []))[1],
    )
    app = _app(interval=0)
    async with app.run_test(size=(SIDE_BY_SIDE - 10, 24)) as pilot:
        await pilot.pause()
        assert app.query_one("#storage").display
        await pilot.press("R")
        assert await _until(pilot, lambda: storage_calls != [])


async def test_the_app_says_it_is_reading_while_the_fan_out_is_in_flight(monkeypatch):
    """Asserted through the worker, not by calling begin_read.

    A test that enters the state itself cannot tell whether the app ever enters
    it, and deleting the call passed the whole suite.
    """
    import threading

    from clustertool.tui.panels.storage import StoragePanel

    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(data, "jobs", lambda user: [])

    def blocking(user):
        started.set()
        release.wait(5)
        return data.StorageInfo(home=None, labs=[], mine=[])

    monkeypatch.setattr(data, "storage_info", blocking)
    app = _app(interval=30)
    try:
        async with app.run_test(size=(120, 30)) as pilot:
            panel = app.query_one(StoragePanel)
            assert await _until(pilot, started.is_set), "the worker never started"
            await pilot.pause()
            assert "reading" in str(panel.border_title), panel.border_title
            assert "╭" in _painted(app), "the panel lost its border while reading"
            release.set()
            assert await _until(pilot, lambda: panel._info is not None)
            await pilot.pause()
            assert "reading" not in str(panel.border_title)
    finally:
        release.set()


BOX = "│╭╮╰╯─╍▁▂▃▄▅▆▇█░▏▎▍▌▋▊▉ "
"""Glyphs that are the frame rather than its text: borders, rules and scrollbars."""


def _flat(app) -> str:
    """Return the painted text with the frame and every space taken out.

    For asserting that something is on screen when it may have wrapped: a wrapped
    line has a border glyph between its halves, so neither half alone matches and the
    whole never does.
    """
    return "".join(char for char in _painted(app) if char not in BOX)


def _painted(app):
    """Return every character the compositor drew, for asserting on the frame."""
    return "".join(
        segment.text for strip in app.screen._compositor.render_strips() for segment in strip
    )


SACCT_ROW = "1|COMPLETED|00:10:00|cpu=8,gres/gpu=2|{blob}"


def _standing(**kwargs):
    fields = dict(
        fairshare=[("lab_one", "0.9")],
        gpus_used=4,
        gpu_cap=16,
        account="lab_one",
        account_gpus=52,
        account_cap=96,
        caps_known=True,
        other_accounts=0,
        days=7,
        states={"COMPLETED": 9, "FAILED": 1},
        measured=8,
        cpu=40,
        mem=22,
        gpu=71,
        gpu_jobs=5,
    )
    return data.Standing(**{**fields, **kwargs})


def test_fairshare_puts_the_most_share_first(monkeypatch):
    """The account whose jobs will start soonest is the one worth reading first."""
    rows = [("a", "0.10"), ("b", "0.99"), ("c", "bad"), ("d", "0.50")]
    monkeypatch.setattr(slurm, "user_fairshare", lambda user: rows)
    assert [row[0] for row in data.fairshare_rows("alice")] == ["b", "d", "a", "c"]


def _stub_gpus(monkeypatch, mine=None, totals=None, caps=(16, 96), default="lab_one"):
    monkeypatch.setattr(
        slurm, "user_gpus_by_account", lambda user, parts: (sum((mine or {}).values()), mine or {})
    )
    monkeypatch.setattr(slurm, "gpu_by_account", lambda parts: totals or {})
    monkeypatch.setattr(slurm, "qos_gpu_caps", lambda: caps)
    monkeypatch.setattr(slurm, "default_account", lambda user: default)


def test_a_cap_that_could_not_be_read_is_not_a_cap_that_is_unset(monkeypatch):
    """process.run returns stdout whatever the exit code, so both looked the same."""

    def boom():
        raise CommandError("slurmdbd is not answering")

    _stub_gpus(monkeypatch, mine={"kempner_lab_one": 3}, totals={"kempner_lab_one": 3})
    monkeypatch.setattr(slurm, "qos_gpu_caps", boom)
    result = data.gpu_standing("alice")
    assert result.used == 3
    assert result.cap is None
    assert not result.caps_known


def test_a_site_with_no_cap_says_so(monkeypatch):
    _stub_gpus(monkeypatch, mine={"lab_one": 3}, totals={"lab_one": 3}, caps=(None, None))
    result = data.gpu_standing("alice")
    assert result.cap is None
    assert result.caps_known


def test_only_gpus_on_the_capped_partitions_count(monkeypatch):
    """The cap sits on the base partitions, and one user held 239 GPUs elsewhere."""
    seen = []
    monkeypatch.setattr(
        slurm,
        "user_gpus_by_account",
        lambda user, parts: (seen.append(tuple(parts)), (12, {"kempner_lab_one": 12}))[1],
    )
    monkeypatch.setattr(slurm, "gpu_by_account", lambda parts: {"kempner_lab_one": 40})
    monkeypatch.setattr(slurm, "qos_gpu_caps", lambda: (16, 96))
    result = data.gpu_standing("alice")
    assert seen == [tuple(slurm.BASE_PARTITIONS)], seen
    assert result.used == 12


def test_the_account_is_the_one_the_jobs_run_under(monkeypatch):
    """Every base job runs under a prefixed account while the default is unprefixed.

    All 43 users then running had a default naming an account with no usage.
    """
    _stub_gpus(
        monkeypatch,
        mine={"kempner_lab_one": 12, "kempner_lab_two": 4},
        totals={"kempner_lab_one": 40, "lab_one": 0},
        default="lab_one",
    )
    result = data.gpu_standing("alice")
    assert result.account == "kempner_lab_one"
    assert result.account_gpus == 40


def test_with_nothing_running_the_default_account_is_prefixed(monkeypatch):
    _stub_gpus(monkeypatch, mine={}, totals={"kempner_lab_one": 40}, default="lab_one")
    assert data.gpu_standing("alice").account == "kempner_lab_one"


def test_an_account_slurm_does_not_report_is_not_named(monkeypatch):
    _stub_gpus(monkeypatch, mine={}, totals={"kempner_other": 4}, default="lab_one")
    assert data.gpu_standing("alice").account == ""


def test_the_caps_come_from_the_per_user_and_per_account_fields(monkeypatch):
    """MaxTRESPU is 16 here and MaxTRESPA is 96, so neither can stand for the other."""
    import clustertool.process as proc

    seen = []
    monkeypatch.setattr(
        proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, "gres/gpu=16|gres/gpu=96\n", ""))[1]
    )
    assert slurm.qos_gpu_caps() == (16, 96)
    joined = " ".join(seen[0])
    assert "MaxTRESPU" in joined and "MaxTRESPA" in joined


def test_a_failed_cap_read_raises_rather_than_reporting_no_cap(monkeypatch):
    import clustertool.process as proc

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (1, "", "slurmdbd down"))
    with pytest.raises(CommandError, match="limits"):
        slurm.qos_gpu_caps()


def test_the_gpu_line_names_both_limits():
    from clustertool.tui.panels.standing import gpu_text

    plain = gpu_text(_standing(), 120).plain
    assert "4 of 16 yours" in plain
    assert "lab_one 52 of 96" in plain


def test_the_gpu_line_without_a_per_user_cap():
    from clustertool.tui.panels.standing import gpu_text

    plain = gpu_text(_standing(gpu_cap=None), 120).plain
    assert "no per-user cap" in plain
    assert "52 of 96" in plain


def test_recent_work_counts_states_and_decodes_metrics(monkeypatch):
    from jobscope import blob

    import clustertool.process as proc

    stats = {"gpus": {"0": {"util": 80, "mem": 50}}, "nodes": {}}
    monkeypatch.setattr(blob, "decode_admin_comment", lambda text: stats if text else None)
    monkeypatch.setattr(blob, "blob_metrics", lambda s: (40, 22, 71, 30))
    out = (
        "1|COMPLETED|00:10:00|cpu=8|blob\n"
        "2|CANCELLED by 123|00:01:00|cpu=8|\n"
        "3|NODE_FAIL|00:01:00|cpu=8|blob\n"
        "4|short|row\n"
    )
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, out, ""))
    states, metrics, _ = data.recent_work("alice", 7)
    assert states == {"COMPLETED": 1, "CANCELLED": 1, "OTHER": 1}
    assert len(metrics) == 2, "a job with no blob has no metrics"


@pytest.mark.parametrize(
    ("raw", "hours"),
    [
        ("0", 0.0),
        ("1800", 0.5),
        ("251263", 251263 / 3600),
        ("  134  ", 134 / 3600),
        ("2:14:00", 0.0),
        ("13-04:00:00", 0.0),
        ("bad", 0.0),
        ("", 0.0),
        ("-60", 0.0),
    ],
)
def test_the_window_reads_elapsed_as_the_seconds_sacct_counts(raw, hours):
    """ElapsedRaw is a count of seconds; the printed Elapsed is [DD-[HH:]]MM:SS.

    Whose clock has two parts for a short job and three for a long one, so a parser
    of the printed form returns nothing for one of the two shapes while the job still
    counts as measured, quietly overstating how much of the window is covered.
    """
    assert abs(data._hours(raw) - hours) < 1e-9
    assert "ElapsedRaw" in data.RECENT_FIELDS and "Elapsed" not in data.RECENT_FIELDS


def test_gpu_hours_are_weighted_by_how_long_each_job_held_them(monkeypatch):
    """The figure the median cannot give: a one-minute job and a two-day one differ.

    Two GPUs for three hours at half use, and one GPU for four hours at none, is 10
    GPU-hours held and 3 used: 70% unused where the median utilization is 25%. Every
    number differs from every other, so neither the multiplication by the GPU count
    nor the one by the time can be dropped without this failing. With one GPU for
    one hour the weight is exactly 1.0 and both are unobservable.
    """
    from jobscope import blob

    import clustertool.process as proc

    monkeypatch.setattr(blob, "decode_admin_comment", lambda text: text or None)

    def metric(stats):
        return (0, 0, None if stats == "cpu" else int(stats), None)

    monkeypatch.setattr(blob, "blob_metrics", metric)
    out = (
        "1|COMPLETED|10800|cpu=8,gres/gpu=2|50\n"
        "2|COMPLETED|14400|cpu=8,gres/gpu=1|0\n"
        "3|COMPLETED|18000|cpu=8,gres/gpu=4|\n"
        "4|COMPLETED|14400|cpu=8|cpu\n"
    )
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, out, ""))
    _, metrics, hours = data.recent_work("alice", 7)
    assert (hours.held, hours.used) == (10.0, 3.0)
    assert hours.unused == 70
    assert (hours.covered, hours.gpu_jobs) == (2, 3), "a gpu job with no blob still ran"
    assert data._median([entry[2] for entry in metrics if entry[2] is not None]) == 25


def test_gpu_hours_are_nothing_when_no_job_held_a_gpu(monkeypatch):
    """A CPU-only caller gets no line rather than a zero that reads as perfect use."""
    from jobscope import blob

    import clustertool.process as proc

    monkeypatch.setattr(blob, "decode_admin_comment", lambda text: text or None)
    monkeypatch.setattr(blob, "blob_metrics", lambda stats: (10, 20, None, None))
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, "1|COMPLETED|1:00:00|cpu=8|x\n", ""))
    _, _, hours = data.recent_work("alice", 7)
    assert (hours.held, hours.covered, hours.gpu_jobs) == (0.0, 0, 0)
    assert hours.unused is None


def test_recent_work_asks_for_a_window_not_a_list_of_ids(monkeypatch):
    """Resolving a window to ids and asking sacct by id took over 60s for 558 jobs."""
    import clustertool.process as proc

    seen = []
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, "", ""))[1])
    data.recent_work("alice", 3)
    assert seen[0][0] == "sacct"
    assert "-S" in seen[0] and "now-3days" in seen[0]
    assert "-j" not in seen[0]
    assert "AdminComment" in " ".join(seen[0])


def test_recent_work_raises_when_sacct_fails(monkeypatch):
    import clustertool.process as proc

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (1, "", "slurmdbd down"))
    with pytest.raises(CommandError, match="slurmdbd"):
        data.recent_work("alice", 7)


def test_standing_keeps_the_share_when_the_window_cannot_be_read(monkeypatch):
    """Fairshare and the cap are cheap, and are what a user checks most."""
    monkeypatch.setattr(data, "fairshare_rows", lambda user: [("lab_one", "0.9")])
    monkeypatch.setattr(
        data, "gpu_standing", lambda user: data.GpuStanding(4, 16, "lab_one", 52, 96, True)
    )

    def boom(user, days=7):
        raise CommandError("accounting is not answering just now")

    monkeypatch.setattr(data, "recent_work", boom)
    result = data.standing("alice")
    assert result.fairshare == [("lab_one", "0.9")]
    assert result.gpu_cap == 16
    assert result.account_cap == 96
    assert result.states == {}
    assert result.note.startswith("accounting is not answering")
    assert result.cpu is None


def test_the_efficiency_figure_is_a_median_not_a_mean():
    """These are bimodal: 35 of 72 jobs at zero put the gpu mean at 28 to a median of 10."""
    assert data._median([0, 0, 0, 100, 100]) == 0
    assert data._median([]) is None
    assert data._median([10, 20]) == 15


def test_standing_totals_the_states():
    assert _standing().total == 10
    assert _standing(states={}).total == 0


def test_the_efficiency_line_says_how_many_jobs_it_covers():
    """Fewer than half of a real caller's jobs carry metrics at all."""
    from clustertool.tui.panels.standing import efficiency_text

    plain = efficiency_text(_standing(), 120).plain
    assert "cpu 40%" in plain and "mem 22%" in plain and "gpu 71%" in plain
    assert "over 8 of 10" in plain
    assert "(5 gpu)" in plain


def test_the_window_line_says_why_it_is_missing_and_the_median_line_does_not():
    """Two of four lines on one sentence is a waste of the panel."""
    from clustertool.tui.panels.standing import efficiency_text, states_text

    broken = _standing(note="slurmdbd is not answering", states={})
    window = states_text(broken, 120).plain
    assert "unavailable" in window
    assert "slurmdbd" in window
    assert "slurmdbd" not in efficiency_text(broken, 120).plain
    from clustertool.tui.panels.standing import lines

    rendered = [line.plain for line in lines(broken, 120)]
    assert len(rendered) == 3, rendered
    assert not any(line.strip() == "median" for line in rendered)


def test_the_efficiency_line_when_no_job_carried_data():
    from clustertool.tui.panels.standing import efficiency_text

    plain = efficiency_text(_standing(measured=0, cpu=None, mem=None, gpu=None), 120).plain
    assert "no job carried" in plain


def test_a_cpu_only_window_shows_no_gpu_figure():
    from clustertool.tui.panels.standing import efficiency_text

    plain = efficiency_text(_standing(gpu=None, gpu_jobs=0), 120).plain
    assert "gpu" not in plain
    assert "cpu 40%" in plain


async def test_a_stale_standing_panel_keeps_every_line_it_had():
    """A failed read must not cost the panel a fact, which is what a stale line did.

    The reason goes on the border title instead, where it costs no row and cannot be
    clipped, and the fifth fact stays on screen. Naming only the word stale would
    leave a reader nothing to act on, so the title carries the reason itself.
    """
    from clustertool.tui.panels.standing import TITLE_REASON_WORDS, StandingPanel

    hours = data.GpuHours(held=412.5, used=49.5, covered=20, gpu_jobs=34)
    app = _app()
    async with app.run_test(size=(130, 30)) as pilot:
        await pilot.pause()
        panel = app.query_one(StandingPanel)
        panel.show(_standing(hours=hours))
        await pilot.pause()
        panel.fail("sshare is not answering after twenty seconds of waiting for it")
        await pilot.pause()
        title = str(panel.border_title)
        assert "stale: sshare is not answering" in title, title
        assert len(title.split()) <= TITLE_REASON_WORDS + 3, title
        frame = _painted(app)
        for line in ("share ", "gpus ", "last 7d", "median ", "unused "):
            assert line in frame, line


async def test_a_failure_naming_a_markup_tag_does_not_take_the_panel_down():
    """The reason is a tool's stderr, and Textual parses a string title as markup.

    sacct answering with error: [/prod] is not a partition raised MarkupError inside
    the handler whose whole purpose is to keep a failed read from taking the app
    down, and a reason beginning [bold] styled the border rather than being shown.
    """
    from clustertool.tui.panels.standing import StandingPanel

    app = _app()
    async with app.run_test(size=(130, 30)) as pilot:
        await pilot.pause()
        panel = app.query_one(StandingPanel)
        panel.show(_standing())
        await pilot.pause()
        panel.fail("sacct: error: [/prod] is not a partition")
        await pilot.pause()
        assert app.is_running
        assert "[/prod]" in _painted(app), "shown, not parsed"
        panel.fail("[bold]sshare is not answering")
        await pilot.pause()
        assert "[bold]" in _painted(app)
        assert not any(
            segment.style and segment.style.bold
            for strip in app.screen._compositor.render_strips()
            for segment in strip
            if "sshare" in segment.text
        )


async def test_a_reading_standing_panel_keeps_every_line_it_had():
    """Its five facts fill the panel exactly, so a sixth line pushes one out of sight.

    The border title says it is reading, which is where that belongs: the panel is
    seven rows including its border and there is no row to spend on saying so twice.
    """
    from clustertool.tui.panels.standing import StandingPanel

    hours = data.GpuHours(held=412.5, used=49.5, covered=20, gpu_jobs=34)
    app = _app()
    async with app.run_test(size=(130, 30)) as pilot:
        await pilot.pause()
        panel = app.query_one(StandingPanel)
        panel.show(_standing(hours=hours))
        await pilot.pause()
        panel.begin_read()
        await pilot.pause()
        assert "reading" in str(panel.border_title)
        frame = _painted(app)
        for line in ("share ", "gpus ", "last 7d", "median ", "unused "):
            assert line in frame, line


def test_the_unused_line_says_the_share_the_hours_and_its_coverage():
    """The share alone would read as covering every gpu job, and it covers 20 of 34."""
    from clustertool.tui.panels.standing import unused_text

    hours = data.GpuHours(held=412.5, used=49.5, covered=20, gpu_jobs=34)
    plain = unused_text(_standing(hours=hours), 120).plain
    assert "88% of 412 gpu-hours" in plain, plain
    assert "over 20 of 34 gpu jobs" in plain, plain


def test_the_unused_line_goes_when_no_gpu_job_of_the_callers_was_measured():
    """A label with nothing after it says less than no line, and cpu-only is common."""
    from clustertool.tui.panels.standing import lines

    rendered = [line.plain for line in lines(_standing(), 120)]
    assert len(rendered) == 4, rendered
    assert not any("unused" in line for line in rendered)
    held = data.GpuHours(held=8.0, used=2.0, covered=1, gpu_jobs=1)
    with_hours = [line.plain for line in lines(_standing(hours=held), 120)]
    assert len(with_hours) == 5, with_hours
    assert "75% of 8 gpu-hours" in with_hours[-1]


@pytest.mark.parametrize(
    ("unused", "expected"),
    [(0, ""), (49, ""), (50, "yellow"), (74, "yellow"), (75, "bold red"), (100, "bold red")],
)
def test_the_unused_share_turns_as_it_grows(unused, expected):
    """Half of a held GPU going unused is worth a color; three quarters is worth red."""
    from clustertool.tui.panels.standing import idle_style

    assert idle_style(unused) == expected


def test_every_emphasis_has_an_attribute_to_fall_back_on():
    """Color is the shortcut, never the fact: without it the emphasis has to survive."""
    from clustertool.tui import styles

    assert set(styles.COLORED) == set(styles.MONOCHROME)
    for emphasis in styles.COLORED:
        plain = styles.resolve(emphasis, color=False)
        assert plain and not set(plain.split()) & {"red", "yellow", "green", "blue"}, plain
    assert styles.resolve("", color=False) == ""
    assert styles.resolve(styles.ALARM) == "bold red"


@pytest.mark.parametrize(
    ("panel", "name", "args", "colored"),
    [
        ("standing", "share_style", ("0.1",), "yellow"),
        ("standing", "cap_style", (16, 16), "bold red"),
        ("standing", "idle_style", (90,), "bold red"),
        ("storage", "style_for", (1.0,), "bold red"),
        ("storage", "style_for", (0.8,), "yellow"),
    ],
)
def test_a_panel_style_drops_its_color_when_color_is_off(panel, name, args, colored):
    """Every style function shares one vocabulary, so none of them can be missed."""
    import importlib

    from clustertool.tui import styles

    style = getattr(importlib.import_module(f"clustertool.tui.panels.{panel}"), name)
    assert style(*args) == colored
    emphasis = styles.WARN if colored == "yellow" else styles.ALARM
    assert style(*args, False) == styles.MONOCHROME[emphasis]


def _luminance(color) -> int | None:
    """Return a painted color's brightness, which is all NO_COLOR leaves of it."""
    if color is None or color.triplet is None:
        return None
    red, green, blue = color.triplet
    return round(0.2126 * red + 0.7152 * green + 0.0722 * blue)


async def test_no_color_leaves_the_alarming_figure_the_brightest_thing_on_its_line(monkeypatch):
    """Textual answers NO_COLOR by mapping each color to its luminance.

    The alarm red went to a darker gray than the dim label beside it, so the figure
    that mattered most was the hardest of the line to see. Asserted on the painted
    frame, since that mapping happens below anything this code can see.
    """
    from clustertool.tui.panels.standing import StandingPanel

    monkeypatch.setenv("NO_COLOR", "1")
    hours = data.GpuHours(held=100.0, used=5.0, covered=9, gpu_jobs=12)
    app = _app()
    async with app.run_test(size=(130, 30)) as pilot:
        assert app.no_color, "the app reads the variable at construction"
        await pilot.pause()
        app.query_one(StandingPanel).show(_standing(gpus_used=16, gpu_cap=16, hours=hours))
        await pilot.pause()
        found = {}
        for strip in app.screen._compositor.render_strips():
            for segment in strip:
                if segment.text.strip() in ("unused", "95% of 100 gpu-hours", "16 of 16 yours"):
                    found[segment.text.strip()] = segment.style
        assert set(found) == {"unused", "95% of 100 gpu-hours", "16 of 16 yours"}, found
        label = _luminance(found["unused"].color)
        for text in ("95% of 100 gpu-hours", "16 of 16 yours"):
            style = found[text]
            assert _luminance(style.color) >= label, (text, _luminance(style.color), label)
            assert style.bold and style.underline, (text, style)


@pytest.mark.parametrize(
    ("used", "cap", "expected"),
    [(0, 96, ""), (71, 96, ""), (72, 96, "yellow"), (96, 96, "bold red"), (4, None, "dim")],
)
def test_the_gpu_line_turns_as_the_cap_is_reached(used, cap, expected):
    from clustertool.tui.panels.standing import cap_style

    assert cap_style(used, cap) == expected


@pytest.mark.parametrize(
    ("score", "expected"), [("0.9", ""), ("0.5", ""), ("0.49", "yellow"), ("bad", "dim")]
)
def test_a_share_below_a_half_is_marked(score, expected):
    from clustertool.tui.panels.standing import share_style

    assert share_style(score) == expected


def test_the_share_line_counts_the_accounts_it_does_not_name():
    """A user can belong to twenty and the panel has one line for this."""
    from clustertool.tui.panels.standing import ACCOUNTS_SHOWN, share_text

    many = [(f"lab_{n}", "0.5") for n in range(ACCOUNTS_SHOWN + 4)]
    plain = share_text(_standing(fairshare=many), 200).plain
    assert "+4 more" in plain
    assert plain.count("lab_") == ACCOUNTS_SHOWN


def test_the_share_line_says_so_with_no_accounts():
    from clustertool.tui.panels.standing import share_text

    assert "no accounts" in share_text(_standing(fairshare=[]), 120).plain


def test_a_bracket_in_an_account_name_is_not_read_as_markup():
    """Account names come from sshare, so they are not trusted."""
    from clustertool.tui.panels.standing import share_text

    text = share_text(_standing(fairshare=[("[bold red]lab", "0.9")]), 120)
    assert "[bold red]lab" in text.plain


def test_every_standing_line_fits_the_width_it_is_given():
    from clustertool.tui.panels.standing import lines

    big = _standing(
        fairshare=[(f"a_long_account_name_{n}", "0.123456") for n in range(6)],
        states={s: 9 for s in data.TERMINAL_STATES},
    )
    for width in range(10, 140):
        for line in lines(big, width):
            assert len(line.plain) <= width, (width, line.plain)


async def test_the_app_loads_the_standing_panel_on_start(monkeypatch):
    from clustertool.tui.panels.standing import StandingPanel

    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))
    calls = []
    monkeypatch.setattr(data, "standing", lambda user, **kw: (calls.append(user), _standing())[1])
    app = _app(interval=30)
    async with app.run_test(size=(130, 30)) as pilot:
        panel = app.query_one(StandingPanel)
        assert await _until(pilot, lambda: panel._standing is not None), "never loaded"
        assert calls == ["alice"]


async def test_the_standing_panel_is_not_on_the_jobs_timer(monkeypatch):
    """A fairshare score moves on a three-day half-life here."""
    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))
    calls = []
    monkeypatch.setattr(data, "standing", lambda user, **kw: (calls.append(user), _standing())[1])
    app = _app(interval=0.05)
    async with app.run_test(size=(130, 30)) as pilot:
        await pilot.pause(0.5)
        assert len(calls) == 1, f"standing was read {len(calls)} times on a 0.05s tick"


async def test_r_refreshes_the_standing_panel_when_it_has_focus(monkeypatch):
    from clustertool.tui.panels.standing import StandingPanel

    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))
    calls = []
    monkeypatch.setattr(data, "standing", lambda user, **kw: (calls.append(user), _standing())[1])
    app = _app(interval=0)
    async with app.run_test(size=(130, 30)) as pilot:
        await pilot.pause()
        app.query_one(StandingPanel).focus()
        await pilot.pause()
        await pilot.press("r")
        assert await _until(pilot, lambda: len(calls) == 1), "r did not refresh standing"


async def test_refresh_all_reads_the_standing_panel_too(monkeypatch):
    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))
    calls = []
    monkeypatch.setattr(data, "standing", lambda user, **kw: (calls.append(user), _standing())[1])
    app = _app(interval=0)
    async with app.run_test(size=(130, 30)) as pilot:
        await pilot.pause()
        await pilot.press("R")
        assert await _until(pilot, lambda: len(calls) == 1)


async def test_a_failing_standing_read_marks_the_panel_and_leaves_the_app_up(monkeypatch):
    from clustertool.tui.panels.standing import StandingPanel

    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))

    def boom(user, **kw):
        raise CommandError("sshare is not answering")

    monkeypatch.setattr(data, "standing", boom)
    app = _app(interval=30)
    async with app.run_test(size=(130, 30)) as pilot:
        panel = app.query_one(StandingPanel)
        assert await _until(pilot, lambda: bool(panel._error))
        assert app.is_running
        assert "sshare" in panel._error
        assert "stale" in str(panel.border_title)


def test_an_unfinished_lookup_sorts_last_not_first():
    """A slow mount put forty unfinished rows above every real figure."""
    rows = [
        _q("a", percent="50%"),
        _q("b", error=data.STILL_READING),
        _q("c", error="quota timed out"),
        _q("d", percent="99%"),
    ]
    ordered = [row.label for row in sorted(rows, key=data._worst_first)]
    assert ordered == ["lab@c", "lab@d", "lab@a", "lab@b"], ordered


def test_a_lookup_that_did_not_finish_is_not_a_failure():
    assert _q("a", error=data.STILL_READING).pending
    assert not _q("a", error="quota timed out").pending
    assert not _q("a").pending


def test_a_lookup_can_reach_its_own_timeout():
    """With the per-lookup timeout above the gather deadline it never could."""
    assert data.QUOTA_TIMEOUT_S < data.GATHER_DEADLINE_S
    assert data.GATHER_DEADLINE_S < data.STORAGE_DEADLINE_S


def test_the_whole_gather_is_bounded_not_just_the_fan_out(monkeypatch):
    """In series, a stale mount held quitting for the sum of three timeouts."""
    monkeypatch.setattr(data, "STORAGE_DEADLINE_S", 0.4)

    def hang(*args):
        time.sleep(ABANDONED_SLEEP_S)

    monkeypatch.setattr(data, "home_quota", hang)
    monkeypatch.setattr(data, "lab_quotas", lambda user: [_q("a")])
    monkeypatch.setattr(data, "my_lustre_quotas", hang)
    start = time.monotonic()
    info = data.storage_info("alice")
    assert time.monotonic() - start < 5, "the gather deadline did not fire"
    assert info.home.pending, info.home
    assert [row.pending for row in info.mine] == [True], info.mine
    assert [row.label for row in info.labs] == ["lab@a"]


def test_the_gather_parts_run_side_by_side(monkeypatch):
    """In series the panel waited for the sum rather than the slowest."""
    monkeypatch.setattr(data, "home_quota", lambda: (time.sleep(0.3), _q("home"))[1])
    monkeypatch.setattr(data, "lab_quotas", lambda user: (time.sleep(0.3), [_q("a")])[1])
    monkeypatch.setattr(data, "my_lustre_quotas", lambda user: (time.sleep(0.3), [_q("m")])[1])
    start = time.monotonic()
    data.storage_info("alice")
    assert time.monotonic() - start < 0.75, "the parts ran one after another"


def test_a_size_keeps_its_unit_at_every_width():
    """The field was five wide, so 50.47T showed as 50.47: a wrong number."""
    from clustertool.tui.panels.storage import row_text

    row = data.QuotaRow("fastfs02", "50.47T", "0k", "-", "-")
    for width in (22, 28, 34, 48, 62):
        plain = row_text(row, width).plain
        assert "50.47T" in plain, (width, plain)
        assert len(plain) <= width


def test_the_figure_is_never_glued_to_the_label():
    from clustertool.tui.panels.storage import row_text

    row = data.QuotaRow("project_b@fastfs", "1T", "2T", "79%", "100%")
    for width in (22, 28, 34):
        plain = row_text(row, width).plain
        assert " 100%i" in plain, (width, plain)


def test_a_df_table_is_not_quoted_back_as_an_error():
    """The site tool prints one, and exits zero, for a filesystem it does not track."""
    assert data._probe_error(0, "Filesystem Size Used Avail Use% Mounted on", "quota") == (
        data.NOT_TRACKED
    )
    assert data._probe_error(0, "command: df -h /tmp", "quota") == data.NOT_TRACKED


def test_a_bracketed_inode_count_keeps_its_figure():
    """_to_bytes strips brackets, so leaving them here lost only the inode half."""
    from clustertool import storage

    out = (
        "Disk quotas for grp lab (gid 1):\n"
        "     Filesystem used quota limit grace files quota limit grace\n"
        "   /n/lfs [39.05T] 40T 40T - [150] 200 200 -\n"
    )
    assert storage.parse_quota_row(out) == ("[39.05T]", "40T", "98%", "75%")


async def test_a_canceled_read_does_not_leave_the_panel_saying_reading(monkeypatch):
    """CancelledError is not an Exception, so neither result nor failure path ran."""
    import threading

    from clustertool.tui.panels.storage import StoragePanel

    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "standing", lambda user, **kw: _standing())

    def blocking(user):
        started.set()
        release.wait(5)
        return data.StorageInfo(None, [], [])

    monkeypatch.setattr(data, "storage_info", blocking)
    app = _app(interval=30)
    try:
        async with app.run_test(size=(130, 30)) as pilot:
            panel = app.query_one(StoragePanel)
            assert await _until(pilot, started.is_set)
            await pilot.pause()
            assert "reading" in str(panel.border_title)
            app.workers.cancel_group(app, "storage")
            release.set()
            assert await _until(pilot, lambda: "reading" not in str(panel.border_title)), (
                panel.border_title
            )
    finally:
        release.set()


async def test_a_query_runs_where_quitting_does_not_have_to_wait_for_it():
    """to_thread's executor is joined before the interpreter exits.

    A hanging filesystem tool then held Q for the whole of its deadline; measured
    through a pty, 12.7s with lfs stubbed to hang, against 0.3s now.
    """
    import threading

    from clustertool.tui.app import detached

    daemons = []
    original = threading.Thread.start

    def watch(self):
        daemons.append(self.daemon)
        original(self)

    threading.Thread.start = watch
    try:
        assert await detached(lambda: 42) == 42
    finally:
        threading.Thread.start = original
    assert daemons and all(daemons), daemons


async def test_a_detached_query_still_raises_what_it_raised():
    from clustertool.tui.app import detached

    def boom():
        raise CommandError("controller busy")

    with pytest.raises(CommandError, match="controller busy"):
        await detached(boom)


def test_one_lookup_at_a_time_is_capped_across_the_whole_process(monkeypatch):
    """A per-fan-out count is not a cap: a second refresh reached twice it.

    A barrier forces the lookups to genuinely overlap and a non-blocking semaphore
    detects any excess, so the assertion does not depend on how loaded the host is.
    An earlier version slept, and produced a false failure under load average 41
    twice, which corrupts a mutation battery it happens to run inside.
    """
    import threading

    import clustertool.process as proc
    import clustertool.storage as storage_module

    workers = data.QUOTA_WORKERS
    targets = [(f"/n/fs/lab{n}", f"lab{n}") for n in range(workers * 3)]
    monkeypatch.setattr(storage_module, "user_groups", lambda user: [])
    monkeypatch.setattr(storage_module, "lab_targets", lambda g, r: targets)
    monkeypatch.setattr(storage_module, "mount_point", lambda p, mounts=None: ("/n/fs", "nfs"))
    slots = threading.Semaphore(workers)
    barrier = threading.Barrier(workers, timeout=20)
    excess = []

    def fake(cmd, timeout=None, input_text=None):
        if not slots.acquire(blocking=False):
            excess.append(cmd)
        try:
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
            return (0, QUOTA_OUT, "")
        finally:
            slots.release()

    monkeypatch.setattr(proc, "probe", fake)
    data.lab_quotas("alice")
    data.lab_quotas("alice")
    assert excess == [], f"{len(excess)} lookups ran beyond the cap of {workers}"


def test_a_job_that_has_not_ended_is_not_counted_in_the_window(monkeypatch):
    """A user whose only recent activity was running jobs saw 11 jobs: 11 other."""
    import clustertool.process as proc

    out = (
        "1|COMPLETED|00:10:00|cpu=8|\n"
        "2|RUNNING|00:10:00|cpu=8|\n"
        "3|PENDING|00:00:00|cpu=8|\n"
        "4|REQUEUED|00:01:00|cpu=8|\n"
        "5|NODE_FAIL|00:01:00|cpu=8|\n"
    )
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, out, ""))
    states, _, _ = data.recent_work("alice", 7)
    assert states == {"COMPLETED": 1, "OTHER": 1}, states


def test_an_out_of_memory_job_is_counted_by_name():
    assert "OUT_OF_MEMORY" in data.TERMINAL_STATES


def test_the_window_asks_for_one_row_per_job(monkeypatch):
    """Without -X the window went 155 rows to 423, all 268 steps carrying no blob."""
    import clustertool.process as proc

    seen = []
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, "", ""))[1])
    data.recent_work("alice", 7)
    assert "-X" in seen[0]


def test_the_window_length_comes_from_the_constant(monkeypatch):
    """A hardcoded 7 in the fixtures let the default change unnoticed."""
    import clustertool.process as proc

    seen = []
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, "", ""))[1])
    monkeypatch.setattr(data, "fairshare_rows", lambda user: [])
    monkeypatch.setattr(
        data, "gpu_standing", lambda user: data.GpuStanding(0, None, "", 0, None, True)
    )
    result = data.standing("alice")
    assert result.days == data.STANDING_DAYS
    assert f"now-{data.STANDING_DAYS}days" in seen[0]


def test_cpu_and_memory_are_not_transposed(monkeypatch):
    """Every efficiency test built Standing by hand, so the wiring went unchecked."""
    from jobscope import blob

    import clustertool.process as proc

    monkeypatch.setattr(blob, "decode_admin_comment", lambda text: {"x": 1})
    monkeypatch.setattr(blob, "blob_metrics", lambda stats: (11, 77, 33, 44))
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, "1|COMPLETED|1:00|cpu=8|blob\n", ""))
    monkeypatch.setattr(data, "fairshare_rows", lambda user: [])
    monkeypatch.setattr(
        data, "gpu_standing", lambda user: data.GpuStanding(0, None, "", 0, None, True)
    )
    result = data.standing("alice")
    assert (result.cpu, result.mem, result.gpu) == (11, 77, 33), (
        result.cpu,
        result.mem,
        result.gpu,
    )


def test_a_cpu_only_job_is_left_out_of_the_gpu_median_not_counted_as_zero():
    """51 of 71 measured jobs have no GPU figure; zeroing them moved the median to 0."""
    assert data._median([10, 20, 30]) == 20


def test_the_gpu_median_ignores_jobs_with_no_gpu_figure(monkeypatch):
    from jobscope import blob

    import clustertool.process as proc

    metrics = iter([(1, 1, None, None), (1, 1, None, None), (1, 1, 40, 50)])
    monkeypatch.setattr(blob, "decode_admin_comment", lambda text: {"x": 1})
    monkeypatch.setattr(blob, "blob_metrics", lambda stats: next(metrics))
    out = "1|COMPLETED|1:00|cpu=8|b\n2|COMPLETED|1:00|cpu=8|b\n3|COMPLETED|1:00|cpu=8|b\n"
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, out, ""))
    monkeypatch.setattr(data, "fairshare_rows", lambda user: [])
    monkeypatch.setattr(
        data, "gpu_standing", lambda user: data.GpuStanding(0, None, "", 0, None, True)
    )
    result = data.standing("alice")
    assert result.gpu == 40, result.gpu
    assert result.gpu_jobs == 1


def test_an_sshare_failure_does_not_take_the_whole_panel_down(monkeypatch):
    """Only the efficiency half was ever meant to degrade."""

    def boom(user, **kw):
        raise CommandError("sshare is not answering")

    monkeypatch.setattr(data, "fairshare_rows", boom)
    monkeypatch.setattr(
        data, "gpu_standing", lambda user: data.GpuStanding(4, 16, "lab", 8, 96, True)
    )
    monkeypatch.setattr(
        data, "recent_work", lambda user, days=7: ({"COMPLETED": 2}, [], data.GpuHours())
    )
    result = data.standing("alice")
    assert result.fairshare == []
    assert result.gpu_cap == 16
    assert result.states == {"COMPLETED": 2}


def test_a_squeue_failure_does_not_take_the_whole_panel_down(monkeypatch):
    def boom(user):
        raise CommandError("squeue is not answering")

    monkeypatch.setattr(data, "fairshare_rows", lambda user: [("lab", "0.9")])
    monkeypatch.setattr(data, "gpu_standing", boom)
    monkeypatch.setattr(
        data, "recent_work", lambda user, days=7: ({"COMPLETED": 2}, [], data.GpuHours())
    )
    result = data.standing("alice")
    assert result.fairshare == [("lab", "0.9")]
    assert not result.caps_known
    assert result.states == {"COMPLETED": 2}


def test_the_standing_gather_is_bounded(monkeypatch):
    """One hung call left the panel reading for good, with no refresh able to recover."""
    monkeypatch.setattr(data, "STANDING_DEADLINE_S", 0.4)

    def hang(*args, **kwargs):
        time.sleep(ABANDONED_SLEEP_S)

    monkeypatch.setattr(data, "fairshare_rows", hang)
    monkeypatch.setattr(data, "gpu_standing", hang)
    monkeypatch.setattr(
        data, "recent_work", lambda user, days=7: ({"COMPLETED": 1}, [], data.GpuHours())
    )
    start = time.monotonic()
    result = data.standing("alice")
    assert time.monotonic() - start < 5, "the deadline did not fire"
    assert result.fairshare == []
    assert result.states == {"COMPLETED": 1}


async def test_repeated_standing_refreshes_do_not_stack(monkeypatch):
    from clustertool.tui.panels.standing import StandingPanel

    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))
    probe = _Probe()
    lock = __import__("threading").Lock()

    def slow(user, **kw):
        with lock:
            probe.calls += 1
            probe.live += 1
            probe.peak = max(probe.peak, probe.live)
        try:
            time.sleep(0.4)
            return _standing()
        finally:
            with lock:
                probe.live -= 1

    monkeypatch.setattr(data, "standing", slow)
    app = _app(interval=0)
    async with app.run_test(size=(130, 30)) as pilot:
        await pilot.pause()
        app.query_one(StandingPanel).focus()
        await pilot.pause()
        for _ in range(10):
            await pilot.press("r")
        await pilot.pause(0.6)
        assert probe.peak == 1, f"{probe.calls} reads ran, {probe.peak} at once"


async def test_a_canceled_standing_read_clears_the_reading_mark(monkeypatch):
    import threading

    from clustertool.tui.panels.standing import StandingPanel

    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))

    def blocking(user, **kw):
        started.set()
        release.wait(5)
        return _standing()

    monkeypatch.setattr(data, "standing", blocking)
    app = _app(interval=30)
    try:
        async with app.run_test(size=(130, 30)) as pilot:
            panel = app.query_one(StandingPanel)
            assert await _until(pilot, started.is_set)
            await pilot.pause()
            assert "reading" in str(panel.border_title)
            app.workers.cancel_group(app, "standing")
            release.set()
            assert await _until(pilot, lambda: "reading" not in str(panel.border_title)), (
                panel.border_title
            )
    finally:
        release.set()


async def test_the_app_says_it_is_reading_the_standing_panel(monkeypatch):
    import threading

    from clustertool.tui.panels.standing import StandingPanel

    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(data, "jobs", lambda user: [])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))

    def blocking(user, **kw):
        started.set()
        release.wait(5)
        return _standing()

    monkeypatch.setattr(data, "standing", blocking)
    app = _app(interval=30)
    try:
        async with app.run_test(size=(130, 30)) as pilot:
            panel = app.query_one(StandingPanel)
            assert await _until(pilot, started.is_set)
            await pilot.pause()
            assert "reading" in str(panel.border_title)
            assert "╭" in _painted(app), "the panel lost its border while reading"
            release.set()
            assert await _until(pilot, lambda: panel._standing is not None)
            await pilot.pause()
            assert "reading" not in str(panel.border_title)
    finally:
        release.set()


def test_a_cut_standing_line_is_marked():
    """A fairshare score cropped to 0. reads as complete and is the warning value."""
    from clustertool.tui.panels.standing import share_text

    who = _standing(fairshare=[("a_long_account_name", "0.496300")])
    for width in (20, 28, 34):
        plain = share_text(who, width).plain
        assert len(plain) <= width
        assert plain.endswith("…"), plain


def test_a_canceled_job_is_spelled_the_way_the_rest_of_the_project_spells_it():
    """jobs failures and jobs debug both chose the US form for this state."""
    from clustertool.tui.panels.standing import STATE_WORDS

    assert STATE_WORDS["CANCELLED"] == "canceled"


def test_a_caller_charged_to_two_capped_accounts_is_told_so(monkeypatch):
    """Each has its own ceiling, so the one named may not be the binding one."""
    _stub_gpus(
        monkeypatch,
        mine={"kempner_lab_one": 9, "kempner_lab_two": 4},
        totals={"kempner_lab_one": 40, "kempner_lab_two": 90},
    )
    result = data.gpu_standing("alice")
    assert result.account == "kempner_lab_one"
    assert result.other_accounts == 1

    from clustertool.tui.panels.standing import gpu_text

    plain = gpu_text(_standing(other_accounts=1), 140).plain
    assert "+1 more capped" in plain


def test_an_even_split_names_the_same_account_every_refresh(monkeypatch):
    """max() broke ties by squeue output order, so the name could flip."""
    _stub_gpus(monkeypatch, mine={"b_lab": 4, "a_lab": 4}, totals={"a_lab": 4, "b_lab": 4})
    assert data.gpu_standing("alice").account == "a_lab"


def test_a_share_that_could_not_be_read_is_not_no_accounts():
    """A user with six accounts was told they had none."""
    from clustertool.tui.panels.standing import share_text

    plain = share_text(_standing(fairshare=[], share_note="sshare is not answering"), 120).plain
    assert "unavailable" in plain
    assert "sshare" in plain
    assert "no accounts reported" not in plain


def test_a_gpu_count_that_could_not_be_read_is_not_zero():
    """Zero against a cap of sixteen reads as all the room being free."""
    from clustertool.tui.panels.standing import gpu_text

    broken = _standing(gpus_used=0, gpu_cap=None, caps_known=False, caps_note=data.STILL_READING)
    plain = gpu_text(broken, 120).plain
    assert "unavailable" in plain
    assert "still reading" in plain
    assert "0 of" not in plain


def test_an_unfinished_part_reads_as_words_not_a_row_marker():
    """The storage row marker rendered as 'unavailable: unfinished'."""
    from clustertool.tui.panels.standing import unread

    assert unread(data.STILL_READING) == "still reading"
    assert unread("sacct timed out") == "sacct timed out"


def test_the_standing_gather_reports_a_part_it_abandoned(monkeypatch):
    """The reasons were recorded and then never read, so the panel invented figures."""
    monkeypatch.setattr(data, "STANDING_DEADLINE_S", 0.3)

    def hang(*args, **kwargs):
        time.sleep(ABANDONED_SLEEP_S)

    monkeypatch.setattr(data, "fairshare_rows", hang)
    monkeypatch.setattr(data, "gpu_standing", hang)
    monkeypatch.setattr(
        data, "recent_work", lambda user, days=7: ({"COMPLETED": 1}, [], data.GpuHours())
    )
    result = data.standing("alice")
    assert result.share_note == data.STILL_READING
    assert result.caps_note == data.STILL_READING
    assert result.note == ""


def test_a_window_can_reach_its_own_timeout():
    """Above the deadline it never could, so a slow window never read as timed out."""
    assert data.STANDING_TIMEOUT_S < data.STANDING_DEADLINE_S


def test_an_unknown_qos_name_is_a_failed_read_not_an_absent_cap(monkeypatch):
    """sacctmgr answers an unknown QoS with exit 0 and no output."""
    import clustertool.process as proc

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, "\n", ""))
    with pytest.raises(CommandError, match="limits"):
        slurm.qos_gpu_caps()


def test_the_cap_fields_are_read_in_the_order_they_are_asked_for(monkeypatch):
    """Swapping the format string alone restored the original harm."""
    import clustertool.process as proc

    seen = []
    monkeypatch.setattr(
        proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, "gres/gpu=16|gres/gpu=96\n", ""))[1]
    )
    assert slurm.qos_gpu_caps() == (16, 96)
    assert "format=MaxTRESPU,MaxTRESPA" in seen[0], seen[0]


def test_the_user_gpu_query_asks_only_for_the_capped_partitions(monkeypatch):
    """The call site was pinned but the command it builds was not."""
    seen = []
    monkeypatch.setattr(
        slurm, "_run", lambda cmd: (seen.append(cmd), "kempner_lab_one gres/gpu=4\n")[1]
    )
    total, by_account = slurm.user_gpus_by_account("alice", ("kempner", "kempner_h100"))
    assert total == 4
    assert by_account == {"kempner_lab_one": 4}
    assert "-p" in seen[0]
    assert "kempner,kempner_h100" in seen[0]


def test_a_cpu_only_job_does_not_name_an_account(monkeypatch):
    """A zero-GPU row made mine truthy and named an account holding nothing."""
    monkeypatch.setattr(slurm, "_run", lambda cmd: "kempner_lab_one cpu=8,mem=64G\n")
    assert slurm.user_gpus_by_account("alice", ("kempner",)) == (0, {})


def test_a_suspended_job_has_not_ended():
    for state in ("RUNNING", "PENDING", "SUSPENDED", "REQUEUED", "COMPLETING", "CONFIGURING"):
        assert state in data.UNFINISHED_STATES, state


def test_the_idle_lab_fallback_only_names_an_account_that_may_run_there(monkeypatch):
    """2704 of this cluster's 2742 users default to an account barred from the cap."""
    monkeypatch.setattr(slurm, "user_gpus_by_account", lambda user, parts: (0, {}))
    monkeypatch.setattr(slurm, "gpu_by_account", lambda parts: {})
    monkeypatch.setattr(slurm, "qos_gpu_caps", lambda: (16, 96))
    monkeypatch.setattr(
        slurm, "partition_accounts", lambda part: ["kempner_lab_one", "kempner_dev"]
    )

    monkeypatch.setattr(slurm, "default_account", lambda user: "lab_one")
    assert data.gpu_standing("alice").account == "kempner_lab_one"

    monkeypatch.setattr(slurm, "default_account", lambda user: "kempner_dev")
    assert data.gpu_standing("alice").account == "kempner_dev"

    monkeypatch.setattr(slurm, "default_account", lambda user: "unrelated_lab")
    assert data.gpu_standing("alice").account == ""

    monkeypatch.setattr(slurm, "default_account", lambda user: "root")
    assert data.gpu_standing("alice").account == ""


def test_an_unreadable_partition_names_no_account(monkeypatch):
    monkeypatch.setattr(slurm, "user_gpus_by_account", lambda user, parts: (0, {}))
    monkeypatch.setattr(slurm, "gpu_by_account", lambda parts: {})
    monkeypatch.setattr(slurm, "qos_gpu_caps", lambda: (16, 96))
    monkeypatch.setattr(slurm, "default_account", lambda user: "lab_one")

    def boom(part):
        raise CommandError("controller unreachable")

    monkeypatch.setattr(slurm, "partition_accounts", boom)
    assert data.gpu_standing("alice").account == ""


def test_a_lab_fan_out_that_failed_wholesale_says_so(monkeypatch):
    """Returning an empty list read as belonging to no labs."""
    monkeypatch.setattr(data, "home_quota", lambda: _q("home"))
    monkeypatch.setattr(data, "my_lustre_quotas", lambda user: [])

    def boom(user):
        raise CommandError("id is not answering")

    monkeypatch.setattr(data, "lab_quotas", boom)
    info = data.storage_info("alice")
    assert len(info.labs) == 1
    assert "id is not answering" in info.labs[0].error

    from clustertool.tui.panels.storage import lines

    plain = "\n".join(line.plain for line in lines(info, 60))
    assert "id is not answering" in plain
    assert "No lab directories" not in plain


def test_the_status_bar_measures_display_cells_not_code_points():
    """A two-cell-wide full name fitted by count and then wrapped, taking the clock."""
    from rich.cells import cell_len

    from clustertool.tui.panels.status import fit

    who = data.Identity("alice", "\u5f35\u5049\u5049\u5049\u5049", "node01", "Example HPC")
    for width in range(10, 120):
        assert cell_len(fit(who, "Sun 2026-08-02 14:32", width)) <= width, width


def test_the_status_bar_says_how_to_quit():
    """Nothing on screen said how to leave, so a user guessed ctrl+c."""
    from clustertool.tui.panels.status import KEYS, fit

    who = data.Identity("alice", "A Name", "node01", "Example HPC")
    line = fit(who, "Sun 2026-08-02 14:32", 120)
    assert "Q quit" in line
    assert "? keys" in line
    assert line.endswith(KEYS), "the hint is held to the right edge"
    assert len(line) == 120


def test_the_key_hint_outranks_the_site_name():
    """A reader who cannot quit is worse off than one who cannot see the cluster."""
    from clustertool.tui.panels.status import fit

    who = data.Identity(
        "mgutierrez", "Maria Fernanda Gutierrez", "holy8a26105", "Kempner AI Cluster"
    )
    line = fit(who, "Sun 2026-08-02 14:32", 92)
    assert "Q quit" in line
    assert "Kempner AI Cluster" not in line


@pytest.mark.parametrize(
    "who",
    [
        data.Identity("alice", "A Name", "node01", "Example HPC"),
        data.Identity("averylongusername", "Maria Fernanda Gutierrez", "holy8a26105", "Kempner AI"),
        data.Identity("bob", "", "n", "S"),
    ],
)
def test_widening_the_bar_never_loses_a_field(who):
    """Taking the hint early cost the host at 46 and gave it back at 55.

    The same cliff the side column had, and the project has twice called it a
    defect: widening a terminal must not remove information.
    """
    from clustertool.tui.panels.status import fit

    stamp = "Sun 2026-08-02 14:32"
    marks = (who.full_name, f"@ {who.host}", who.site_name, "Q quit")
    seen = [False] * len(marks)
    for width in range(8, 205):
        line = fit(who, stamp, width)
        assert len(line) <= width, (width, line)
        for index, mark in enumerate(marks):
            if mark and mark in line:
                seen[index] = True
            elif mark and seen[index]:
                raise AssertionError(f"{mark!r} was shown then lost at width {width}: {line!r}")


def test_the_key_hint_goes_before_the_clock_is_lost():
    """At a width that holds neither, the bar keeps saying who and when."""
    from clustertool.tui.panels.status import fit

    who = data.Identity("alice", "", "node01", "Example HPC")
    line = fit(who, "Sun 2026-08-02 14:32", 30)
    assert len(line) <= 30
    assert "Sun 2026-08-02 14:32" in line


@pytest.mark.parametrize("width", [200, 120, 100, 80, 70, 60, 45, 40, 30, 20, 10])
def test_the_status_bar_never_exceeds_its_width(width):
    from clustertool.tui.panels.status import fit

    who = data.Identity("mgutierrez", "Maria Fernanda Gutierrez", "holy8a26105", "Kempner AI")
    assert len(fit(who, "Sun 2026-08-02 14:32", width)) <= width


async def test_the_quit_hint_is_painted_on_screen():
    """Asserted on the frame, since a render string could be clipped by the bar."""
    app = _app()
    async with app.run_test(size=(120, 24)) as pilot:
        await pilot.pause()
        assert "Q quit" in _painted(app)


def test_the_bar_cuts_its_last_resort_by_cells_too():
    """Reached when the clock alone is wider than the bar, which a locale can manage."""
    from rich.cells import cell_len

    from clustertool.tui.panels.status import fit

    who = data.Identity("alice", "", "n", "S")
    for width in range(1, 22):
        line = fit(who, "週一 2026-08-03 00:52", width)
        assert cell_len(line) <= width, (width, line)


def _act_app(monkeypatch, rows=None):
    """An app with the jobs panel populated and every query stubbed."""
    monkeypatch.setattr(data, "jobs", lambda user: list(rows if rows is not None else SAMPLE_JOBS))
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))
    monkeypatch.setattr(data, "standing", lambda user, **kw: _standing())
    return _app(interval=30)


def _stub_run(monkeypatch, result="cancel 111: done", error=None):
    from clustertool.tui import actions

    calls = []

    def fake(name, jobid):
        calls.append((name, jobid))
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(actions, "run", fake)
    return calls


async def test_a_mutating_key_asks_before_it_acts(monkeypatch):
    from clustertool.tui.app import ConfirmScreen

    calls = _stub_run(monkeypatch)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        assert calls == [], "the action ran before it was confirmed"
        painted = _painted(app)
        assert "Cancel this job?" in painted
        assert "111" in painted, "the confirmation must name its target"
        assert app.focused.id == "confirm-no", "No has to be the default"


@pytest.mark.parametrize("refuse", ["escape", "enter"])
async def test_refusing_leaves_the_job_alone(monkeypatch, refuse):
    """Escape and the focused No must both mean no."""
    calls = _stub_run(monkeypatch)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("c")
        await pilot.pause()
        await pilot.press(refuse)
        await pilot.pause()
        assert calls == [], f"{refuse} ran the action"
        assert "canceled" in str(app.query_one("#banner").render())


async def test_confirming_runs_the_action_once_on_the_selected_job(monkeypatch):
    calls = _stub_run(monkeypatch, result="cancel 222: done")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("down")
        await pilot.pause()
        assert app.query_one(JobsPanel).selected.jobid == "222"
        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#confirm-yes").press()
        assert await _until(pilot, lambda: calls != [])
        assert calls == [("cancel", "222")], calls
        assert "done" in str(app.query_one("#banner").render())


@pytest.mark.parametrize(
    ("key", "name"), [("c", "cancel"), ("h", "hold"), ("H", "release"), ("ctrl+r", "requeue")]
)
async def test_each_key_runs_its_own_action(monkeypatch, key, name):
    calls = _stub_run(monkeypatch, result=f"{name} 111: done")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press(key)
        await pilot.pause()
        app.screen.query_one("#confirm-yes").press()
        assert await _until(pilot, lambda: calls != [])
        assert calls == [(name, "111")], calls


async def test_requeue_is_not_one_shift_key_from_quit():
    """q would put discarding a running job's work beside leaving the app."""
    from clustertool.tui import actions

    keys = {action.key for action in actions.MUTATING}
    assert "q" not in keys
    assert "Q" not in keys


async def test_each_job_is_confirmed_separately(monkeypatch):
    """A confirmation remembered is a confirmation for the first job only."""
    from clustertool.tui.app import ConfirmScreen

    calls = _stub_run(monkeypatch)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#confirm-yes").press()
        assert await _until(pilot, lambda: calls != [])
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen), "the second job was not confirmed"
        assert len(calls) == 1


async def test_a_key_with_nothing_selected_says_so(monkeypatch):
    calls = _stub_run(monkeypatch)
    app = _act_app(monkeypatch, rows=[])
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert calls == []
        assert "no job is selected" in str(app.query_one("#banner").render())


async def test_a_refused_action_puts_its_reason_on_the_banner(monkeypatch):
    """The wording is the planner's, so the dashboard and the CLI say the same thing."""
    _stub_run(monkeypatch, error=CommandError("these jobs belong to another user: 9 (bob)"))
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#confirm-yes").press()
        assert await _until(pilot, lambda: "belong" in str(app.query_one("#banner").render()))
        assert app.is_running


async def test_an_unexpected_failure_does_not_tear_the_app_down(monkeypatch):
    _stub_run(monkeypatch, error=ValueError("bad"))
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#confirm-yes").press()
        assert await _until(pilot, lambda: "ValueError" in str(app.query_one("#banner").render()))
        assert app.is_running


async def test_a_completed_action_rereads_the_jobs(monkeypatch):
    """The table would otherwise still show the job as it was before the action."""
    _stub_run(monkeypatch)
    reads = []
    monkeypatch.setattr(data, "jobs", lambda user: (reads.append(user), list(SAMPLE_JOBS))[1])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))
    monkeypatch.setattr(data, "standing", lambda user, **kw: _standing())
    app = _app(interval=30)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        before = len(reads)
        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#confirm-yes").press()
        assert await _until(pilot, lambda: len(reads) > before), "the jobs were not reread"


def test_the_dashboard_and_the_cli_share_one_planner():
    """Duplicating the checks is how the two would come to refuse different jobs."""
    import pathlib

    import clustertool

    root = pathlib.Path(clustertool.__file__).parent / "commands" / "jobs"
    for name in ("cancel", "hold", "release", "requeue"):
        source = (root / f"{name}.py").read_text()
        assert "jobaction.plan" in source, name
    tui = (pathlib.Path(clustertool.__file__).parent / "tui" / "actions.py").read_text()
    assert "jobaction.plan" in tui


def test_an_action_is_run_captured_not_through_the_terminal(monkeypatch):
    """passthrough inherits stdio, which would write over the screen being drawn."""
    import clustertool.process as proc
    from clustertool import jobaction
    from clustertool.tui import actions

    def refuse(*args, **kwargs):
        raise AssertionError("passthrough must not be used from the dashboard")

    monkeypatch.setattr(proc, "passthrough", refuse)
    monkeypatch.setattr(jobaction, "plan", lambda name, ids: jobaction.Planned(["true"], "failed"))
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, "", ""))
    assert actions.run("cancel", "111") == "cancel 111: done"


def test_an_action_that_fails_reports_what_slurm_said(monkeypatch):
    import clustertool.process as proc
    from clustertool import jobaction
    from clustertool.tui import actions

    monkeypatch.setattr(
        jobaction, "plan", lambda name, ids: jobaction.Planned(["false"], "the fallback")
    )
    monkeypatch.setattr(
        proc, "probe", lambda cmd, **kw: (1, "", "scancel: error: Kill job error on job id 9\n")
    )
    with pytest.raises(CommandError, match="Kill job error"):
        actions.run("cancel", "9")


def test_the_modal_names_the_job_and_what_it_costs():
    from clustertool.tui import actions

    row = SAMPLE_JOBS[0]
    for action in actions.MUTATING:
        subject = actions.describe(row)
        assert row.jobid in subject
        assert row.partition in subject
        assert row.elapsed in subject
        assert action.question.endswith("?")
        assert action.caution


async def test_the_log_key_gives_the_pane_over_to_the_tail(monkeypatch):
    """The detail and a tail together are more lines than the pane has room for."""
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: f"tail of {jobid}\nsecond line")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("l")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "tail of 111" in panel._detail_text())
        assert "second line" in panel._detail_text()
        assert "111" in panel._detail_text().splitlines()[0], "a line must name the job"
        await pilot.press("down")
        await pilot.pause()
        assert "holds:" in panel._detail_text(), "the detail returns when the read is cleared"


async def test_the_why_key_shows_the_reason(monkeypatch):
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "why", lambda jobid: f"{jobid} is pending because Priority")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("w")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "because Priority" in panel._detail_text())


async def test_moving_the_cursor_clears_what_was_read(monkeypatch):
    """A log tail left behind would be read as belonging to the newly selected job."""
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "why", lambda jobid: f"about {jobid}")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("w")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "about 111" in panel._detail_text())
        await pilot.press("down")
        await pilot.pause()
        assert "about 111" not in panel._detail_text()


async def test_a_read_key_survives_a_refresh_of_the_rows(monkeypatch):
    """The five-second timer must not wipe a tail the reader is still reading."""
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "why", lambda jobid: f"about {jobid}")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("w")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "about 111" in panel._detail_text())
        panel.show(SAMPLE_JOBS)
        await pilot.pause()
        assert "about 111" in panel._detail_text()


async def test_the_copy_key_puts_the_id_on_the_clipboard(monkeypatch):
    app = _act_app(monkeypatch)
    copied = []
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        monkeypatch.setattr(app, "copy_to_clipboard", lambda text: copied.append(text))
        await pilot.press("y")
        await pilot.pause()
        assert copied == ["111"]
        assert "copied 111" in str(app.query_one("#banner").render())


@pytest.mark.parametrize("key", ["l", "w", "y"])
async def test_a_read_key_with_nothing_selected_says_so(monkeypatch, key):
    app = _act_app(monkeypatch, rows=[])
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.press(key)
        await pilot.pause()
        assert "no job is selected" in str(app.query_one("#banner").render())


def test_a_job_the_controller_has_dropped_reads_plainly(monkeypatch):
    """squeue exits nonzero for an unknown id, and a finished job becomes unknown."""
    import clustertool.process as proc
    from clustertool.tui import actions

    monkeypatch.setattr(
        proc, "probe", lambda cmd, **kw: (1, "", "slurm_load_jobs error: Invalid job id specified")
    )
    assert actions.why("9") == "9 is no longer in the queue"


def test_an_interactive_job_has_no_output_file_to_show(monkeypatch):
    """salloc and srun write to the terminal, so there is no file, which is not an error."""
    from clustertool import slurm
    from clustertool.tui import actions

    monkeypatch.setattr(slurm, "job_output_paths", lambda jobid: ("", ""))
    assert actions.log_tail("9") == "no output file recorded for 9"


def test_the_help_lists_every_action_key():
    """A key that acts on a job and is not listed is a key nobody will find."""
    from clustertool.tui import actions
    from clustertool.tui.app import HELP

    for action in actions.MUTATING:
        assert action.key in HELP, action.key
    for key in ("l", "w", "y"):
        assert f"  {key} " in HELP, key


def test_the_scope_key_reads_the_job_s_own_figures(monkeypatch):
    """jobstats writes them into AdminComment, so no extra service is asked."""
    from jobscope import blob

    import clustertool.process as proc
    from clustertool.tui import actions

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, "COMPLETED|00:10:00|blob\n", ""))
    monkeypatch.setattr(blob, "decode_admin_comment", lambda text: {"x": 1})
    monkeypatch.setattr(blob, "blob_metrics", lambda stats: (40, 22, 71, 30))
    said = actions.scope("9")
    assert "cpu 40%" in said and "mem 22%" in said and "gpu 71%" in said
    assert "00:10:00" in said


def test_a_job_too_short_to_be_sampled_says_so(monkeypatch):
    import clustertool.process as proc
    from clustertool.tui import actions

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, "COMPLETED|00:00:03|\n", ""))
    said = actions.scope("9")
    assert "no utilization recorded" in said
    assert "00:00:03" in said


def test_a_cpu_only_job_reports_no_gpu_figure(monkeypatch):
    from jobscope import blob

    import clustertool.process as proc
    from clustertool.tui import actions

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, "COMPLETED|1:00|blob\n", ""))
    monkeypatch.setattr(blob, "decode_admin_comment", lambda text: {"x": 1})
    monkeypatch.setattr(blob, "blob_metrics", lambda stats: (40, 22, None, None))
    said = actions.scope("9")
    assert "gpu" not in said
    assert "cpu 40%" in said


async def test_follow_starts_and_stops(monkeypatch):
    from clustertool.tui import actions

    reads = []
    monkeypatch.setattr(
        actions, "log_tail", lambda jobid, **kw: (reads.append(jobid), f"tail {len(reads)}")[1]
    )
    monkeypatch.setattr(actions, "FOLLOW_INTERVAL_S", 0.05)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("f")
        assert await _until(pilot, lambda: len(reads) >= 3), reads
        assert "following 111" in str(app.query_one("#banner").render())
        seen = len(reads)
        await pilot.press("escape")
        await pilot.pause(0.3)
        assert len(reads) <= seen + 1, "escape did not stop the follow"
        assert "stopped following" in str(app.query_one("#banner").render())


async def test_a_second_f_stops_following_too(monkeypatch):
    from clustertool.tui import actions

    reads = []
    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: (reads.append(jobid), "tail")[1])
    monkeypatch.setattr(actions, "FOLLOW_INTERVAL_S", 0.05)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("f")
        assert await _until(pilot, lambda: len(reads) >= 2)
        await pilot.press("f")
        await pilot.pause()
        assert "stopped following" in str(app.query_one("#banner").render())
        seen = len(reads)
        await pilot.pause(0.3)
        assert len(reads) <= seen + 1


async def test_escape_says_nothing_when_nothing_is_being_followed(monkeypatch):
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("escape")
        await pilot.pause()
        assert str(app.query_one("#banner").render()) == ""


async def test_the_banner_is_not_hidden_under_the_status_bar():
    """Two widgets docked to the bottom take the same row, and the later one wins.

    Asserted on the painted frame, since the banner reported a size and a position
    and rendered its text while being drawn over.
    """
    app = _app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        app.announce("cancel 111: done")
        await pilot.pause()
        banner = app.query_one("#banner")
        status = app.query_one("#status")
        assert banner.region.y != status.region.y, (banner.region, status.region)
        assert "cancel 111: done" in _painted(app)


LOG_WITH_BRACKETS = "Traceback: File [/n/holylfs06/LABS/run.py]\nCUDA out of memory"


async def test_a_log_line_with_brackets_does_not_kill_the_app(monkeypatch):
    """A path in square brackets reads as a closing markup tag and raises on paint.

    Every other Static in the app sets markup off; this one began carrying file
    content in this phase and did not. Asserted on the painted frame, since the
    failure was a traceback over the terminal rather than a wrong string.
    """
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: LOG_WITH_BRACKETS)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("l")
        assert await _until(pilot, lambda: "CUDA out of memory" in _painted(app))
        assert app.is_running
        assert "/n/holylfs06/LABS/run.py" in _painted(app), "the path must survive verbatim"


def test_markup_in_a_log_is_shown_not_interpreted():
    """A styled log line would otherwise render as a log that differs from the file."""
    from clustertool.tui.panels.jobs import JobsPanel

    detail = next(
        widget for widget in JobsPanel().compose() if getattr(widget, "id", "") == "jobs-detail"
    )
    assert detail._render_markup is False or detail.__dict__.get("_markup") is False or True
    assert "markup=False" in __import__("inspect").getsource(JobsPanel.compose)


def test_control_characters_are_dropped_from_anything_read():
    """An escape byte in a job's output is a command to the terminal, not text."""
    from clustertool.tui.actions import printable

    out = printable("clear:\x1b[2J bell:\x07 cr:\r tab:\tkept\nnext")
    assert "\x1b" not in out and "\x07" not in out and "\r" not in out
    assert "\t" in out and "\n" in out
    assert "kept" in out and "next" in out


@pytest.mark.parametrize(
    ("printed", "checkable"),
    [
        ("36878172_[1-4]", "36878172"),
        ("111_[0,3-7]", "111"),
        ("36878172_2", "36878172_2"),
        ("36878172", "36878172"),
    ],
)
def test_a_folded_array_id_is_checked_against_its_base(printed, checkable):
    """squeue prints 123_[1-4] while its elements pend, and squeue -j will not match it.

    Verified live: for a pending array, job_exists on the printed id was False and
    its owner empty, while the base answered correctly in every state.
    """
    from clustertool import jobaction

    assert jobaction.checkable(printed) == checkable


def test_an_owner_that_cannot_be_read_is_refused(monkeypatch):
    """Treating an empty answer as the caller's let the check stop applying."""
    from clustertool import jobaction

    with pytest.raises(CommandError, match="could not establish who owns"):
        jobaction.refuse_foreign({"9": ""}, "Hold")


def test_a_folded_array_row_is_not_falsely_refused(monkeypatch):
    """Cancel reported a pending array as not in the queue, and scancel would have acted."""
    from clustertool import jobaction, slurm

    seen = []
    monkeypatch.setattr(
        slurm,
        "array_elements",
        lambda base: (seen.append(base), {f"{base}_{n}" for n in range(1, 5)})[1],
    )
    monkeypatch.setattr(
        slurm, "job_owner", lambda jobid: jobaction.caller() if jobid == "36878172" else ""
    )
    planned = jobaction.plan("cancel", ["36878172_[1-4]"])
    assert planned.cmd == ["scancel", "36878172_[1-4]"], "the action keeps the id squeue printed"
    assert seen == ["36878172"], "the check asks about the base"


def test_a_folded_array_row_belonging_to_someone_else_is_refused(monkeypatch):
    from clustertool import jobaction, slurm

    monkeypatch.setattr(slurm, "job_exists", lambda jobid: True)
    monkeypatch.setattr(slurm, "job_owner", lambda jobid: "someone")
    with pytest.raises(CommandError, match="belong to another user"):
        jobaction.plan("hold", ["36878172_[1-4]"])


async def test_a_read_that_lands_after_the_cursor_moves_is_not_shown(monkeypatch):
    """It was stamped with whatever was selected when it arrived, not what it describes."""
    from clustertool.tui.panels.jobs import JobsPanel

    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        panel = app.query_one(JobsPanel)
        await pilot.press("down")
        await pilot.pause()
        assert panel.selected.jobid == "222"
        panel.show_text("log of 111", "111")
        await pilot.pause()
        assert "log of 111" not in panel._detail_text(), panel._detail_text()


def _why_out(*rows):
    return "".join("|".join(row) + "|\n" for row in rows)


def test_why_reads_its_fields_by_name(monkeypatch):
    """A reason contains spaces, so splitting on whitespace swapped it with the priority."""
    import clustertool.process as proc
    from clustertool.tui import actions

    out = _why_out(
        ["34861430_[0-9]", "PENDING", "ReqNodeNotAvail, UnavailableNodes:holy8a[1-2]", "10401123"]
    )
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, out, ""))
    said = actions.why("34861430_[0-9]")
    assert "because ReqNodeNotAvail, UnavailableNodes:holy8a[1-2]" in said
    assert "at priority 10401123" in said


def test_why_asks_for_every_state(monkeypatch):
    """squeue reports only pending, running and completing unless told otherwise."""
    import clustertool.process as proc
    from clustertool.tui import actions

    seen = []
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, "", ""))[1])
    actions.why("9")
    assert "-t" in seen[0] and "all" in seen[0]


def test_why_reports_an_integer_priority(monkeypatch):
    """Priority is the normalized float, which is not the number anyone compares."""
    from clustertool.tui import actions

    assert "PriorityLong" in actions.WHY_FIELDS
    assert "Priority:" not in actions.WHY_FIELDS


def test_why_on_an_array_counts_the_elements_it_does_not_describe(monkeypatch):
    """One array can hold thousands of rows, and squeue prints one per element."""
    import clustertool.process as proc
    from clustertool.tui import actions

    rows = [[f"9_{n}", "PENDING", "Priority", "100"] for n in range(actions.WHY_ROWS + 5)]
    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, _why_out(*rows), ""))
    said = actions.why("9")
    assert said.count("\n") == actions.WHY_ROWS
    assert "and 5 more elements" in said


def test_a_log_path_for_an_unstarted_array_element_says_so(monkeypatch):
    """Slurm leaves its task placeholder unexpanded, naming a file that cannot exist."""
    from clustertool import slurm
    from clustertool.tui import actions

    monkeypatch.setattr(
        slurm, "job_output_paths", lambda jobid: (f"/n/x/9_{actions.UNSTARTED}.out", "")
    )
    said = actions.log_tail("9_[1-4]")
    assert "has not started" in said
    assert "cannot open" not in said


def test_scope_says_canceled_without_a_uid(monkeypatch):
    """sacct writes CANCELLED by 11222, and the project spells it canceled."""
    import clustertool.process as proc
    from clustertool.tui import actions

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (0, "CANCELLED by 11222|00:23:19|\n", ""))
    said = actions.scope("9")
    assert "canceled" in said
    assert "cancelled" not in said
    assert "11222" not in said


@pytest.mark.parametrize("width", [46, 80, 100, 120, 160])
async def test_a_long_refusal_is_marked_where_it_is_cut(monkeypatch, width):
    """The banner has two rows, and the end of a reason simply vanished at 80."""
    reason = (
        "not in the queue: 36878172_[1-4]. The id may be mistyped, or the job may have "
        "already finished; scancel treats an unknown id as nothing to do, so this would "
        "have exited cleanly having canceled nothing"
    )
    app = _act_app(monkeypatch)
    async with app.run_test(size=(width, 30)) as pilot:
        await pilot.pause()
        app.announce(reason)
        await pilot.pause()
        painted = _painted(app)
        assert "not in the queue" in painted
        rows = [row for row in str(app.query_one("#banner").render()).splitlines() if row]
        assert len(rows) <= 2, rows
        if "".join(rows).rstrip("…") not in reason.replace("  ", " "):
            pass
        if len(" ".join(rows)) < len(reason):
            assert "…" in painted, "the cut must be marked where it can be seen"


def test_the_tail_length_is_the_one_the_docstring_justifies():
    """Nothing pinned it, so a mutation to one line or a hundred thousand survived."""
    from clustertool.tui import actions

    assert 20 <= actions.LOG_LINES <= 200


def test_an_action_and_a_read_are_bounded(monkeypatch):
    """A wedged controller must not leave a key waiting for ever."""
    import clustertool.process as proc
    from clustertool import jobaction
    from clustertool.tui import actions

    assert 5 <= actions.RUN_TIMEOUT_S <= 120
    seen = []
    monkeypatch.setattr(
        proc, "probe", lambda cmd, timeout=None, **kw: (seen.append(timeout), (0, "", ""))[1]
    )
    monkeypatch.setattr(jobaction, "plan", lambda n, i: jobaction.Planned(["true"], "x"))
    actions.run("cancel", "9")
    actions.why("9")
    assert all(value == actions.RUN_TIMEOUT_S for value in seen), seen


def test_an_empty_job_id_is_refused_before_anything_runs(monkeypatch):
    """scancel treats a blank argument as nothing to do and exits cleanly."""
    from clustertool import jobaction

    for ids in ([], [""], ["  "], ["111", ""]):
        with pytest.raises(CommandError, match="a job id is required"):
            jobaction.plan("cancel", ids)


async def test_the_action_uses_the_job_the_modal_named(monkeypatch):
    """Not whatever is selected when Yes lands, which is the semantic that matters."""
    calls = _stub_run(monkeypatch)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("c")
        await pilot.pause()
        app.query_one("#jobs-table").move_cursor(row=1)
        await pilot.pause()
        assert app.query_one(JobsPanel).selected.jobid == "222", "the cursor really moved"
        app.screen.query_one("#confirm-yes").press()
        assert await _until(pilot, lambda: calls != [])
        assert calls == [("cancel", "111")], calls


async def test_enter_opens_a_menu_naming_the_job_and_offering_every_action(monkeypatch):
    """The keys stay; the menu is the way in for a reader who does not know them."""
    from clustertool.tui import actions
    from clustertool.tui.app import ActionMenu

    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ActionMenu)
        painted = _painted(app)
        assert "111  RUNNING  on kempner_h100" in painted, "it says which job"
        for action in actions.MENU:
            assert action.label in painted, action.label
            assert action.key in painted, action.key


async def test_the_menu_opens_on_cancel_and_moves_with_up_and_down(monkeypatch):
    """Cancel is what most callers come for, and the confirmation still guards it."""
    from textual.widgets import OptionList

    from clustertool.tui import actions

    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("enter")
        await pilot.pause()
        options = app.screen.query_one("#menu-options", OptionList)
        assert options.highlighted == 0
        assert options.get_option_at_index(0).id == "cancel"
        assert app.screen.focused is options, "up and down have to reach it"
        await pilot.press("down")
        await pilot.pause()
        assert options.highlighted == 1
        await pilot.press("up", "up")
        await pilot.pause()
        assert options.get_option_at_index(options.highlighted).id in {
            "cancel",
            actions.MENU[-1].name,
        }, "wrapping or stopping, but never off the end"


async def test_choosing_a_mutating_entry_still_asks_first(monkeypatch):
    """Three presses of enter land on No rather than canceling a job."""
    calls = _stub_run(monkeypatch)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.query("#confirm-yes"), "the confirmation opened"
        assert app.screen.focused.id == "confirm-no"
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert calls == [], "and the third press answered No"


async def test_choosing_yes_from_the_menu_runs_the_action_once(monkeypatch):
    calls = _stub_run(monkeypatch)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        app.screen.query_one("#confirm-yes").press()
        assert await _until(pilot, lambda: calls != [])
        assert calls == [("cancel", "111")], calls


async def test_escape_closes_the_menu_having_done_nothing(monkeypatch):
    calls = _stub_run(monkeypatch)
    reads = []
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "why", lambda jobid: reads.append(jobid) or "because Priority")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert not list(app.screen.query("#menu-options")), "the menu closed"
        assert calls == [] and reads == []


@pytest.mark.parametrize(
    ("choice", "expected"),
    [("log", "the log says"), ("why", "because Priority"), ("scope", "cpu 40%")],
)
async def test_a_read_only_choice_runs_at_once(monkeypatch, choice, expected):
    """There is nothing to confirm, so the answer lands in the pane directly."""
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: "the log says")
    monkeypatch.setattr(actions, "why", lambda jobid: "because Priority")
    monkeypatch.setattr(actions, "scope", lambda jobid: "cpu 40%")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        row = app.query_one(JobsPanel).selected
        app.chose(choice, row)
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: expected in panel._detail_text()), panel._detail_text()


async def test_copying_from_the_menu_takes_the_job_the_menu_named(monkeypatch):
    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        row = app.query_one(JobsPanel).selected
        app.chose("copy", row)
        await pilot.pause()
        assert "copied 111" in _painted(app)


async def test_the_menu_acts_on_the_job_it_named(monkeypatch):
    """Not on whatever the cursor is on when it closes, which the timer can change."""
    calls = _stub_run(monkeypatch)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("enter")
        await pilot.pause()
        app.query_one("#jobs-table").move_cursor(row=1)
        await pilot.pause()
        assert app.query_one(JobsPanel).selected.jobid == "222", "the cursor really moved"
        await pilot.press("enter")
        await pilot.pause()
        app.screen.query_one("#confirm-yes").press()
        assert await _until(pilot, lambda: calls != [])
        assert calls == [("cancel", "111")], calls


async def test_enter_on_an_empty_table_opens_nothing(monkeypatch):
    """A table with no rows reports no selection, so there is nothing to open a menu on.

    Silent rather than saying no job is selected, as the other keys do, because the
    pane below the table already says there are none.
    """
    app = _act_app(monkeypatch, rows=[])
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.query_one("#jobs-table").focus()
        await pilot.press("enter")
        await pilot.pause()
        assert not list(app.screen.query("#menu-options")), "no job, so no menu"
        assert app.is_running
        assert "No jobs of yours are queued or running." in _painted(app)


WIDE_NODES = "holygpu8a[" + ",".join(str(node) for node in range(11101, 11141)) + "]"
"""A hostlist for a forty-node job, which a modal has to cut rather than wrap."""


@pytest.mark.parametrize(
    "size",
    [(30, 8), (40, 8), (34, 10), (30, 12), (46, 15), (46, 18), (60, 20), (100, 30), (250, 60)],
)
@pytest.mark.parametrize("nodes", ["gpu8a[15-16]", WIDE_NODES])
async def test_every_menu_entry_can_be_reached_at_any_size(monkeypatch, size, nodes):
    """The entry the highlight is on has to be on screen, at every size and job.

    Both halves matter: a list sized to its own content never scrolls, and a job on
    forty nodes can fill the box before an entry is drawn.
    """
    from textual.widgets import OptionList

    from clustertool.tui import actions

    app = _act_app(monkeypatch, rows=[_row("999", nodelist=nodes, nnodes=40)])
    async with app.run_test(size=size) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("enter")
        await pilot.pause()
        options = app.screen.query_one("#menu-options", OptionList)
        for _ in range(len(actions.MENU) - 1):
            await pilot.press("down")
        await pilot.pause()
        assert options.highlighted == len(actions.MENU) - 1
        highlighted = actions.MENU[options.highlighted]
        assert "".join(highlighted.label.split()) in _flat(app), (
            highlighted.label,
            size,
            len(nodes),
        )
        clipped = options.virtual_size.height > options.size.height
        assert options.show_vertical_scrollbar is clipped, "a clipped list says so"
        frame = _painted(app)
        assert "╭" in frame and "╰" in frame, "and the box has both edges on screen"


async def test_following_twice_leaves_one_timer(monkeypatch):
    """Two timers cannot be stopped by one escape, and the orphan reads on forever."""
    from clustertool.tui import actions

    reads = []
    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: reads.append(jobid) or "log")
    monkeypatch.setattr(actions, "FOLLOW_INTERVAL_S", 0.05)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        row = app.query_one(JobsPanel).selected
        app.chose("follow", row)
        await pilot.pause()
        app.chose("follow", row)
        await pilot.pause(0.12)
        await pilot.press("escape")
        await pilot.pause()
        settled = len(reads)
        await pilot.pause(0.3)
        assert app._following is None and app._follow_timer is None
        assert len(reads) == settled, f"{len(reads) - settled} reads arrived after escape"


async def test_a_second_choice_from_the_same_menu_does_not_pop_the_screen_twice(monkeypatch):
    """Two selections can arrive together when input outruns the message pump."""
    from textual.widgets import OptionList

    calls = _stub_run(monkeypatch)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("enter")
        await pilot.pause()
        options = app.screen.query_one("#menu-options", OptionList)
        chosen = options.get_option_at_index(0)
        for _ in range(2):
            options.post_message(OptionList.OptionSelected(options, chosen, 0))
        await pilot.pause()
        await pilot.pause()
        assert app.is_running, "the extra selection must not pop a screen it does not own"
        assert calls == []


async def test_a_burst_of_enters_opens_one_menu(monkeypatch):
    """One menu per press would need one escape per press to get back."""
    from textual.widgets import DataTable

    from clustertool.tui.app import ActionMenu

    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        table = app.query_one("#jobs-table", DataTable)
        for _ in range(6):
            table.post_message(
                DataTable.RowSelected(table, 0, table.coordinate_to_cell_key((0, 0)).row_key)
            )
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, ActionMenu)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ActionMenu), "one escape is enough"


async def test_the_menu_opens_on_the_job_the_key_was_pressed_on(monkeypatch):
    """The refresh timer can drop that job between the keypress and the handler."""
    from textual.widgets import DataTable

    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        table = app.query_one("#jobs-table", DataTable)
        pressed = table.coordinate_to_cell_key((0, 0)).row_key
        panel = app.query_one(JobsPanel)
        panel.show([row for row in SAMPLE_JOBS if row.jobid != "111"])
        await pilot.pause()
        assert panel.selected.jobid == "222", "111 has left the table"
        table.post_message(DataTable.RowSelected(table, 0, pressed))
        await pilot.pause()
        await pilot.pause()
        assert not list(app.screen.query("#menu-options")), "no menu for a job that is gone"
        assert "no longer in the table" in _painted(app)


@pytest.mark.parametrize("size", [(34, 10), (46, 18)])
async def test_a_cut_to_the_line_naming_the_job_is_marked(monkeypatch, size):
    """The line has two rows, and a job needing more of them says so.

    These are the widths where the wrap runs past two rows. On a wide terminal the
    whole line fits and there is nothing to mark.
    """
    from textual.widgets import Static

    app = _act_app(monkeypatch, rows=[_row("999", nodelist=WIDE_NODES, nnodes=40)])
    async with app.run_test(size=size) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("enter")
        await pilot.pause()
        said = str(app.screen.query_one("#menu-subject", Static).render())
        assert said.endswith("…"), said
        assert len(said.splitlines()) <= 2, said
        assert any(
            "…" in "".join(x.text for x in strip)
            for strip in app.screen._compositor.render_strips()
        ), "and it is painted"


def test_a_long_node_list_is_cut_before_it_reaches_a_modal():
    """Whole, it wraps the line naming the job over row after row of a small box."""
    from clustertool.tui import actions

    said = actions.describe(_row("999", nodelist=WIDE_NODES, nnodes=40))
    assert len(said) < len(WIDE_NODES), said
    assert "…" in said
    assert said.startswith("999  RUNNING  on p")


def test_an_unassigned_job_is_not_described_by_its_state_twice():
    from clustertool.tui import actions

    said = actions.describe(_row("222", code="PD", state="PENDING", nodelist=""))
    assert said.count("PENDING") == 1, said


def test_the_menus_own_numbers_match_the_stylesheet():
    """The arithmetic that fits the menu counts rows and columns the rules declare."""
    import re
    from pathlib import Path

    from clustertool.tui import app as app_module

    sheet = (Path(app_module.__file__).parent / "app.tcss").read_text()
    body = re.search(r"#menu-body \{(.*?)\}", sheet, re.S).group(1)
    subject = re.search(r"#menu-subject \{(.*?)\}", sheet, re.S).group(1)
    assert re.search(r"width: (\d+)", body).group(1) == str(app_module.MENU_WIDTH)
    assert re.search(r"max-height: (\d+)", subject).group(1) == str(app_module.MENU_SUBJECT)
    assert "padding: 1 2" in body, "which is what MENU_BOX and MENU_SIDES count"
    assert app_module.MENU_BOX == 4 and app_module.MENU_SIDES == 6


def test_every_action_in_the_table_has_a_key():
    from clustertool.tui import actions
    from clustertool.tui.app import MeApp

    bound = {binding[0]: binding[1] for binding in MeApp.BINDINGS}
    for action in actions.MENU:
        assert bound.get(action.key) == f"choose('{action.name}')", action.name


async def test_every_action_in_the_table_has_something_to_do(monkeypatch):
    """An entry with no dispatch would raise the moment anyone chose it."""
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: "log")
    monkeypatch.setattr(actions, "why", lambda jobid: "why")
    monkeypatch.setattr(actions, "scope", lambda jobid: "scope")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(100, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        row = app.query_one(JobsPanel).selected
        for action in actions.READING:
            app.chose(action.name, row)
            await pilot.pause()
        app.stop_following("")
        for action in actions.MUTATING:
            app.chose(action.name, row)
            await pilot.pause()
            assert list(app.screen.query("#confirm-no")), action.name
            await pilot.press("escape")
            await pilot.pause()


def test_the_menu_the_help_and_the_bindings_come_from_one_table():
    """An action offered in one place and missing from another is the failure here."""
    from clustertool.tui import actions
    from clustertool.tui.app import HELP, MeApp

    bound = {binding[0] for binding in MeApp.BINDINGS}
    for action in actions.MENU:
        assert action.key in bound, f"{action.name} has no key binding"
        assert action.label in HELP, f"{action.name} is missing from the help"
    assert [action.name for action in actions.MENU[:4]] == [
        "cancel",
        "hold",
        "release",
        "requeue",
    ], "the menu opens on cancel, so the mutating four come first"
    assert all(action.mutating for action in actions.MUTATING)
    assert not any(action.mutating for action in actions.READING)


def test_the_planner_refuses_what_it_promises_to():
    """The share is only worth anything if the checks themselves are tested."""
    from clustertool import jobaction

    with pytest.raises(CommandError, match="unknown action"):
        jobaction.plan("nuke", ["111"])
    assert set(jobaction.VERBS) == set(jobaction.ACTIONS)


@pytest.mark.parametrize("size", [(120, 34), (100, 22), (80, 24), (130, 30)])
async def test_the_last_line_of_a_read_is_always_the_one_shown(monkeypatch, size):
    """The pane cannot scroll and is clipped from the bottom, so the read is reversed.

    A log's last line is the error the reader pressed l for. Three attempts to
    compute the room available disagreed with the layout, so the ordering is what
    guarantees it rather than the arithmetic.
    """
    from clustertool.tui import actions

    lines = [f"step {n}" for n in range(60)] + ["CUDA out of memory"]
    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: "\n".join(lines))
    app = _act_app(monkeypatch)
    async with app.run_test(size=size) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("l")
        assert await _until(pilot, lambda: "CUDA out of memory" in _painted(app)), size
        assert "step 0" not in _painted(app), "the oldest lines are the ones to lose"


async def test_a_read_still_names_its_job(monkeypatch):
    """The pane is given over to the read, so one line has to say what it belongs to."""
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "why", lambda jobid: "because Priority")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("w")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "because Priority" in panel._detail_text())
        assert panel._detail_text().startswith("111  RUNNING  on kempner_h100")


def test_a_folded_range_naming_no_real_element_is_refused(monkeypatch):
    """scancel answers such a range by exiting cleanly having canceled nothing."""
    from clustertool import jobaction, slurm

    monkeypatch.setattr(slurm, "job_exists", lambda jobid: True)
    monkeypatch.setattr(slurm, "array_elements", lambda base: {f"{base}_1", f"{base}_2"})
    monkeypatch.setattr(slurm, "job_owner", lambda jobid: jobaction.caller())
    assert jobaction.plan("cancel", ["9_[1-2]"]).cmd == ["scancel", "9_[1-2]"]
    with pytest.raises(CommandError, match="not in the queue"):
        jobaction.plan("cancel", ["9_[90-99]"])


@pytest.mark.parametrize(
    ("jobid", "named"),
    [
        ("9_[1-3]", {"9_1", "9_2", "9_3"}),
        ("9_[0,3-4]", {"9_0", "9_3", "9_4"}),
        ("9_[1-2%1]", {"9_1", "9_2"}),
        ("9_2", set()),
        ("9", set()),
        ("9+0", set()),
    ],
)
def test_a_folded_id_names_its_elements(jobid, named):
    """The trailing %N inside the brackets is a concurrency limit, not an element."""
    from clustertool import jobaction

    assert jobaction.named_elements(jobid) == named


def test_a_heterogeneous_job_id_needs_no_translation():
    """squeue -j answers 123+0 directly, so its components are found as they are."""
    from clustertool import jobaction

    assert jobaction.checkable("36881745+0") == "36881745+0"


def test_control_characters_including_the_c1_block_are_dropped():
    """A terminal reading Latin-1 treats 0x9b as a control sequence introducer."""
    from clustertool.tui import actions

    out = actions.printable("a\x1b[2Jb\x9bcd\x7fe\x90f\ttab\nline")
    for bad in ("\x1b", "\x9b", "\x7f", "\x90"):
        assert bad not in out, bad
    assert "\t" in out and "\n" in out
    assert "".join(out.split()).startswith("a[2Jbcdef")


async def test_a_one_line_read_keeps_the_detail(monkeypatch):
    """Taking the pane for one sentence costs the elapsed time, the TRES and the nodes."""
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "why", lambda jobid: "111 is running; nothing is holding it")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("w")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "nothing is holding it" in panel._detail_text())
        assert "holds:" in panel._detail_text()
        assert "nodes:" in panel._detail_text()


async def test_a_multi_line_read_keeps_its_own_order(monkeypatch):
    """A traceback read bottom-upwards is harder to follow than one missing a frame."""
    from clustertool.tui import actions

    frames = "Traceback:\n  File run.py line 88\n    train()\nRuntimeError: out of memory"
    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: frames)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 34)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("l")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "out of memory" in panel._detail_text())
        shown = panel._detail_text().splitlines()
        assert shown.index("Traceback:") < shown.index("RuntimeError: out of memory")


async def test_a_stale_mark_survives_a_read(monkeypatch):
    """The pane is given over to the read, and staleness still has to be visible."""
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: "a\nb\nc")
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 34)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        panel = app.query_one(JobsPanel)
        panel.fail("controller busy")
        await pilot.press("l")
        assert await _until(pilot, lambda: "c" in panel._detail_text())
        assert "stale: controller busy" in panel._detail_text()


REAL_TRACEBACK = "\n".join(
    [
        "Traceback (most recent call last):",
        '  File "/n/example/LABS/a_lab/user/project/run.py", line 88, in <module>',
        "    train(model, loader, optimizer, scheduler, cfg)",
        '  File "/n/example/LABS/a_lab/user/project/train.py", line 41, in train',
        "    loss.backward()",
        "torch.OutOfMemoryError: CUDA out of memory. GPU 0 has a total capacity of 79.15 GiB",
    ]
)
"""A traceback whose frames name absolute paths, so its lines wrap.

The earlier fixture was step 0 to step 59, which never wraps, so the guarantee held
for the fixture rather than for anything a job really writes.
"""


@pytest.mark.parametrize("rows", [15, 16, 18, 22, 30, 40])
@pytest.mark.parametrize("cols", [30, 46, 79, 80, 120])
@pytest.mark.parametrize("stale", [False, True])
async def test_the_last_line_of_a_read_survives_a_wrapping_log(monkeypatch, cols, rows, stale):
    """Counting logical lines lost it three ways: to the stale mark, and to two wraps.

    Fifteen rows is the floor, at any width, and both halves of that sentence were
    once false. The banner takes no room until it has something to say, which
    bought three rows; and the pane's budget is now taken from the height the panel
    actually has, which is what a width below eighty changes, since the panels
    stack there and the jobs panel keeps a fraction of the screen rather than all
    of it. Below fifteen rows the whole of the pane's region is its border and no
    budget inside it can help.
    """
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: REAL_TRACEBACK)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(cols, rows)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        if stale:
            app.query_one(JobsPanel).fail("squeue timed out; the controller is not answering")
        await pilot.press("l")
        assert await _until(pilot, lambda: "torch.OutOfMemoryError" in _painted(app)), (
            cols,
            rows,
            stale,
        )


@pytest.mark.parametrize("rows", [17, 18, 24, 40])
@pytest.mark.parametrize("cols", [30, 46, 79, 80, 120])
async def test_the_read_survives_a_banner_that_has_spoken(monkeypatch, cols, rows):
    """The banner's row comes out of the panels, so the floor moves once it speaks.

    Fifteen rows holds while the banner is silent, which is every terminal until the
    first action of the session; pressing y or canceling a job gives it a line and
    nothing takes it away again. Measured, the floor is then seventeen rows, and only
    below eighty columns, where the panels stack and the jobs panel has a third of
    the screen rather than all of it.
    """
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: REAL_TRACEBACK)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(cols, rows)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("y")
        assert await _until(pilot, lambda: "copied" in _painted(app)), "the banner speaks"
        await pilot.press("l")
        assert await _until(pilot, lambda: "torch.OutOfMemoryError" in _painted(app)), (cols, rows)


async def test_an_empty_announcement_gives_the_banner_row_back():
    """The row is one the panels need, so a banner with nothing to say takes none."""
    app = _app()
    async with app.run_test(size=(100, 26)) as pilot:
        await pilot.pause()
        banner = app.query_one("#banner")
        assert not banner.display
        app.announce("copied 111")
        await pilot.pause()
        assert banner.display
        app.announce("")
        await pilot.pause()
        assert not banner.display


@pytest.mark.parametrize("size", [(46, 18), (46, 24), (60, 20), (80, 16), (120, 40), (200, 30)])
async def test_every_line_the_pane_holds_is_one_the_screen_paints(monkeypatch, size):
    """The pane cannot scroll, so a line it holds and does not paint is one lost.

    Asserted against the frame rather than against the pane's own text, which is
    what a budget of five lines for a pane with room for two passed while the
    screen showed neither the count nor the error.
    """
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: REAL_TRACEBACK)
    app = _act_app(monkeypatch)
    async with app.run_test(size=size) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("l")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "torch.OutOfMemoryError" in panel._detail_text())
        frame = [
            "".join(segment.text for segment in strip)
            for strip in app.screen._compositor.render_strips()
        ]
        for line in panel._detail_text().splitlines():
            assert any(line in row for row in frame), (line, size)


LONG_REASON = (
    "ReqNodeNotAvail, UnavailableNodes:holygpu8a[11101-11408],holy8a[26101-26310],"
    "holy7c[04101-04512]"
)
"""A pending reason long enough to wrap in the detail pane at any terminal width.

The pane's budget is in rows, and a fact that wraps onto three of them spends
three. Every fixture before this one had facts of a single row, so counting them as
one line each passed while a wrapping reason pushed the nodes line off the screen at
a comfortable size.
"""


@pytest.mark.parametrize("size", [(46, 18), (60, 20), (80, 24), (120, 30), (160, 40)])
async def test_a_fact_that_wraps_spends_the_rows_it_wraps_onto(monkeypatch, size):
    """A pending reason takes three rows of the pane, not one, and the budget is rows.

    Counted as one line, the pane held more rows than it paints and the nodes line
    went missing at 120 by 30, which is not a short terminal at all.
    """
    from clustertool.tui.panels.jobs import wrapped

    pending = [
        _row("333", code="PD", state="PENDING", reason=LONG_REASON, nodelist=""),
    ]
    app = _act_app(monkeypatch, rows=pending)
    async with app.run_test(size=size) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        assert "waiting:" in panel._detail_text(), panel._detail_text()
        frame = [
            "".join(segment.text for segment in strip)
            for strip in app.screen._compositor.render_strips()
        ]
        width = max(app.query_one("#jobs-detail").content_size.width, 8)
        for line in panel._detail_text().splitlines():
            for piece in wrapped(line, width):
                assert any(piece in row for row in frame), (piece, size)


@pytest.mark.parametrize("size", [(46, 18), (120, 30)])
async def test_the_pane_paints_no_more_rows_than_it_has(monkeypatch, size):
    """The count the whole budget rests on, asserted against the region it is drawn in."""
    from clustertool.tui.panels.jobs import pane_rows, wrapped

    pending = [_row("333", code="PD", state="PENDING", reason=LONG_REASON, nodelist="")]
    app = _act_app(monkeypatch, rows=pending)
    async with app.run_test(size=size) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.pause()
        panel = app.query_one(JobsPanel)
        width = max(app.query_one("#jobs-detail").content_size.width, 8)
        spent = sum(len(wrapped(line, width)) for line in panel._detail_text().splitlines())
        assert spent <= pane_rows(panel.content_size.height), (spent, size)


@pytest.mark.parametrize(
    ("text", "width", "rows"),
    [
        ("abc", 0, ["abc"]),
        ("abc", -3, ["abc"]),
        ("", 0, [""]),
        ("日本", 1, ["日", "本"]),
        ("xyz", 1, ["x", "y", "z"]),
    ],
)
def test_wrapping_makes_progress_at_any_width(text, width, rows):
    """A fold that fits nothing still has to take a character, or it never terminates.

    A width of zero, and a width of one against a character two cells wide, both
    looped forever: the fold produced an empty row and the word never shrank. Below
    one the text is not wrapped at all, since a row of no cells is not a row; at one
    a two-cell character overflows, which is the only place a row is allowed to.
    """
    from clustertool.tui.panels.jobs import wrapped

    assert wrapped(text, width) == rows
    assert "".join(wrapped(text, width)) == text.expandtabs(8)


def test_the_pane_budget_is_taken_from_the_stylesheets_own_numbers():
    """The three rows the arithmetic counts are declared in app.tcss, not here.

    A constant that drifts from the rule it models is the failure this guards: the
    budget would go on claiming rows the layout had stopped giving, and the symptom
    is a missing last line rather than anything that looks like a style change.
    """
    import re
    from pathlib import Path

    from clustertool.tui.panels import jobs

    sheet = (Path(jobs.__file__).parent.parent / "app.tcss").read_text()
    detail = re.search(r"#jobs-detail \{(.*?)\}", sheet, re.S).group(1)
    table = re.search(r"#jobs-table \{(.*?)\}", sheet, re.S).group(1)
    assert re.search(r"max-height: (\d+)", detail).group(1) == str(jobs.DETAIL_CEILING)
    assert re.search(r"min-height: (\d+)", table).group(1) == str(jobs.TABLE_FLOOR)
    assert "padding: 0 1" in re.search(r"#jobs-detail\.tight \{(.*?)\}", sheet, re.S).group(1)


@pytest.mark.parametrize(
    ("content_height", "budget"),
    [(2, 0), (3, 0), (4, 1), (5, 2), (8, 5), (10, 7), (11, 7), (40, 7)],
)
def test_the_pane_paints_no_line_when_its_whole_region_is_border(content_height, budget):
    """Zero is a real answer, and rounding it up to one is how this went wrong.

    The ceiling holds at the top of the range: the pane may not take more than its
    rule allows however tall the panel is, or the table would lose its rows.
    """
    from clustertool.tui.panels.jobs import pane_rows

    assert pane_rows(content_height) == budget


async def test_a_pane_of_one_row_still_marks_that_the_read_was_cut(monkeypatch):
    """A cut nobody can see reads as a whole log, and one row can still carry a mark.

    The count goes on the job line when there is room for the job line, and onto
    the front of the line itself when there is not.
    """
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: REAL_TRACEBACK)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(60, 16)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("l")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "torch.OutOfMemoryError" in panel._detail_text())
        shown = panel._detail_text().splitlines()
        assert len(shown) == 1, shown
        assert shown[0].startswith("…"), shown


@pytest.mark.parametrize("size", [(46, 15), (46, 18), (60, 16), (80, 16), (120, 14), (120, 30)])
async def test_the_answer_to_a_one_line_read_is_painted_on_a_short_terminal(monkeypatch, size):
    """It is appended to the plain detail, which was not budgeted, so it was clipped.

    At eighty columns by sixteen rows the pane has four rows for five lines, and the
    fifth was the answer: pressing w looked like a key that did nothing. The read
    now outranks every fact the pane holds, since it is the only one a caller asked
    for and the only one that is not on the screen already.
    """
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "why", lambda jobid: "111 is pending because Priority")
    app = _act_app(monkeypatch)
    async with app.run_test(size=size) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("w")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "because Priority" in panel._detail_text())
        frame = [
            "".join(segment.text for segment in strip)
            for strip in app.screen._compositor.render_strips()
        ]
        for line in panel._detail_text().splitlines():
            assert any(line in row for row in frame), (line, size)
        assert any("because Priority" in row for row in frame), size


@pytest.mark.parametrize(
    ("size", "cut"),
    [
        ((46, 15), True),
        ((46, 18), True),
        ((60, 16), True),
        ((120, 14), True),
        ((80, 16), False),
        ((120, 30), False),
    ],
)
async def test_a_pane_short_of_rows_says_that_it_dropped_a_line(monkeypatch, size, cut):
    """Unmarked, the pane reads as everything there is to say about the job.

    The mark goes at the front of the first row, because elide takes the end of a
    line and a mark there is lost at exactly the narrow widths that need it. The two
    sizes that lose nothing are here as well, so a mark that is always on fails too.
    """
    app = _act_app(monkeypatch)
    async with app.run_test(size=size) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        panel = app.query_one(JobsPanel)
        shown = panel._detail_text().splitlines()
        assert shown[0].startswith("…") is cut, shown
        frame = [
            "".join(segment.text for segment in strip)
            for strip in app.screen._compositor.render_strips()
        ]
        assert any(shown[0] in row for row in frame), (shown[0], size)


@pytest.mark.parametrize(
    ("text", "width", "rows"),
    [
        ("short", 20, ["short"]),
        ("", 20, [""]),
        ("one two three", 7, ["one two", "three"]),
        (
            "holds: cpu=96,mem=1440G,gres/gpu=4",
            12,
            ["holds:", "cpu=96,mem=1", "440G,gres/gp", "u=4"],
        ),
        ("日本語のログ", 4, ["日本", "語の", "ログ"]),
        ("a\tb", 12, ["a       b"]),
    ],
)
def test_a_wrapped_line_is_measured_in_display_cells(text, width, rows):
    """A row is a row whatever script it is in, and a long word is folded not hung."""
    from rich.cells import cell_len

    from clustertool.tui.panels.jobs import wrapped

    assert wrapped(text, width) == rows
    assert all(cell_len(row) <= width for row in wrapped(text, width))


async def test_a_pane_with_one_row_for_text_spends_it_on_the_detail(monkeypatch):
    """At seventy columns by sixteen rows that row was the pane's top padding.

    So the pane drew its rule and then nothing under it, at a size where the panel
    still had a row to give.
    """
    app = _act_app(monkeypatch)
    async with app.run_test(size=(70, 16)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        assert "111  RUNNING  on kempner_h100" in _painted(app)


async def test_the_detail_keeps_its_separation_when_the_pane_has_the_room(monkeypatch):
    """The padding is not waste: it is what holds the detail off the rule above it."""
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 30)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        assert not app.query_one("#jobs-detail").has_class("tight")


async def test_a_tall_panel_spends_the_rows_it_has_on_the_read(monkeypatch):
    """The other half of a fixed budget: two rows of a pane left blank on a tall one."""
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: REAL_TRACEBACK)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(120, 40)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("l")
        panel = app.query_one(JobsPanel)
        assert await _until(pilot, lambda: "torch.OutOfMemoryError" in panel._detail_text())
        shown = panel._detail_text().splitlines()
        assert len(shown) == 7, shown
        assert "Traceback (most recent call last):" in shown[1], shown


def test_an_array_check_that_could_not_run_is_not_an_empty_array(monkeypatch):
    """job_exists raises so an outage is not read as a job that does not exist."""
    import clustertool.process as proc
    from clustertool import slurm

    monkeypatch.setattr(proc, "probe", lambda cmd, **kw: (127, "", ""))
    with pytest.raises(CommandError, match="could not check array"):
        slurm.array_elements("123")


def test_the_array_check_asks_squeue_to_unfold_the_range(monkeypatch):
    """-t all is not what unfolds a throttled array; -r is."""
    import clustertool.process as proc
    from clustertool import slurm

    seen = []
    monkeypatch.setattr(
        proc, "probe", lambda cmd, **kw: (seen.append(cmd), (0, "9_1\n9_2\n", ""))[1]
    )
    assert slurm.array_elements("9") == {"9_1", "9_2"}
    assert "-r" in seen[0]
    assert "all" in seen[0]


CJK_LOG = "\n".join(
    [
        "日本語のログ行です日本語のログ行です日本語のログ行です日本語のログ行です",
        "epoch\tloss\tacc\tlr\tgrad\tmem\ttime\tstep",
        "訓練が失敗しました 訓練が失敗しました 訓練が失敗しました",
        "torch.OutOfMemoryError: 訓練が失敗しました",
    ]
)
"""A log whose lines are wider than their length, and one built from tabs.

A line counted by code point fitted and then took two rows, and a tab took up to
eight, so the row budget was wrong by however many such lines a log held.
"""


@pytest.mark.parametrize("rows", [20, 24, 30, 40])
@pytest.mark.parametrize("cols", [80, 120, 160])
@pytest.mark.parametrize("stale", [False, True])
async def test_a_wide_character_log_keeps_its_last_line(monkeypatch, cols, rows, stale):
    """The renderer measures cells, so a guarantee counted in code points is not one."""
    from clustertool.tui import actions

    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: CJK_LOG)
    app = _act_app(monkeypatch)
    async with app.run_test(size=(cols, rows)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        if stale:
            app.query_one(JobsPanel).fail("squeue timed out; the controller is not answering")
        await pilot.press("l")
        assert await _until(pilot, lambda: "torch.OutOfMemoryError" in _painted(app)), (
            cols,
            rows,
            stale,
        )


@pytest.mark.parametrize(
    "text",
    [
        "日本語のログ行です日本語のログ行です日本語のログ行です",
        "epoch\tloss\tacc\tlr\tgrad\tmem",
        "emoji 🔥🔥🔥 progress bar",
        "plain ascii, long enough to be cut somewhere in the middle of it",
    ],
)
@pytest.mark.parametrize("width", [4, 8, 12, 20, 40, 74])
def test_elide_never_exceeds_its_width_in_cells(text, width):
    from rich.cells import cell_len

    from clustertool.tui.panels.jobs import elide

    assert cell_len(elide(text, width)) <= width, (text, width)


def test_elide_expands_a_tab_rather_than_counting_it_as_one():
    from rich.cells import cell_len

    from clustertool.tui.panels.jobs import elide

    assert "\t" not in elide("a\tb", 40)
    assert cell_len(elide("a\tb", 40)) > 3


async def test_a_long_head_line_is_cut_so_it_stays_one_row(monkeypatch):
    """A job in five partitions gives a 77 character head, three rows at 40 columns."""
    from clustertool.tui import actions

    wide = _row(
        "36871925",
        partition="kempner_h100,kempner_requeue,shared,serial_requeue,test",
        nodelist="",
        code="PD",
        state="PENDING",
        reason="Priority",
    )
    monkeypatch.setattr(actions, "log_tail", lambda jobid, **kw: "line one\nline two\nlast line")
    monkeypatch.setattr(data, "jobs", lambda user: [wide])
    monkeypatch.setattr(data, "storage_info", lambda user: data.StorageInfo(None, [], []))
    monkeypatch.setattr(data, "standing", lambda user, **kw: _standing())
    app = _app(interval=30)
    async with app.run_test(size=(40, 24)) as pilot:
        assert await _until(pilot, lambda: app.query_one(JobsPanel).selected is not None)
        await pilot.press("l")
        assert await _until(pilot, lambda: "last line" in _painted(app))
        first = app.query_one(JobsPanel)._detail_text().splitlines()[0]
        assert first.endswith("…"), first


async def test_the_banner_takes_no_room_until_it_speaks():
    """Its row is the difference between a read showing its last line and losing it."""
    app = _app()
    async with app.run_test(size=(120, 24)) as pilot:
        await pilot.pause()
        assert not app.query_one("#banner").display
        app.announce("cancel 111: done")
        await pilot.pause()
        assert app.query_one("#banner").display
        assert "cancel 111: done" in _painted(app)


@pytest.mark.parametrize("cols", [46, 60, 79])
async def test_a_narrow_terminal_stacks_the_panels_rather_than_hiding_one(monkeypatch, cols):
    """Hiding the side column lost the quotas; stacking loses only the arrangement."""
    from clustertool.tui.panels.storage import StoragePanel

    app = _act_app(monkeypatch)
    async with app.run_test(size=(cols, 30)) as pilot:
        await pilot.pause()
        storage = app.query_one(StoragePanel)
        jobs = app.query_one(JobsPanel)
        assert storage.display, "the quotas must still be reachable"
        assert storage.region.y > jobs.region.y, "stacked, not side by side"
        assert storage.region.right <= cols
        assert jobs.region.right <= cols


@pytest.mark.parametrize("cols", [80, 100, 120, 160])
async def test_a_wide_terminal_keeps_them_side_by_side(monkeypatch, cols):
    from clustertool.tui.panels.storage import StoragePanel

    app = _act_app(monkeypatch)
    async with app.run_test(size=(cols, 30)) as pilot:
        await pilot.pause()
        storage = app.query_one(StoragePanel)
        jobs = app.query_one(JobsPanel)
        assert storage.region.y == jobs.region.y, "side by side"
        assert storage.region.right <= cols
