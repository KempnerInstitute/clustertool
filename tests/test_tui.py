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


def test_run_starts_the_app(monkeypatch):
    from clustertool.tui import app as app_module

    started = []
    monkeypatch.setattr(app_module.MeApp, "run", lambda self: started.append(self))
    app_module.run(identity=data.Identity("alice", "", "node01", "Example HPC"))
    assert len(started) == 1


FIXED_CLOCK = datetime.datetime(2026, 8, 2, 14, 32)


def _app(full_name="A Name", interval=0):
    """Build the app with the timer off, so a shell test never asks a scheduler.

    With the timer on, these ran squeue for real: they passed on a login node and
    failed anywhere without Slurm, where the panel comes up marked stale.
    """
    from clustertool.tui.app import MeApp

    return MeApp(
        identity=data.Identity("alice", full_name, "node01", "Example HPC"),
        clock=lambda: FIXED_CLOCK,
        interval=interval,
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


async def test_the_side_column_goes_away_before_it_is_drawn_off_screen():
    """Two panels with width floors overflow a narrow terminal, and the second is lost."""
    from clustertool.tui.app import SIDE_BY_SIDE

    app = _app()
    async with app.run_test(size=(SIDE_BY_SIDE, 14)) as pilot:
        await pilot.pause()
        assert app.query_one("#storage").display
        assert app.query_one("#jobs").region.right <= SIDE_BY_SIDE
        await pilot.resize_terminal(SIDE_BY_SIDE - 4, 14)
        await pilot.pause()
        assert not app.query_one("#storage").display
        assert app.query_one("#jobs").region.right <= SIDE_BY_SIDE - 4
        await pilot.resize_terminal(100, 14)
        await pilot.pause()
        assert app.query_one("#storage").display


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
        assert long_reason in panel._detail_text()
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
    assert storage.mount_point("/n/holylfs06/LABS/kempner_dev", mounts) == (
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
        assert not panel.loading


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
        assert not panel.loading


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
        assert not panel.loading


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
    """or -1 collapsed the two, and fourteen of the real forty rows sit at nought."""
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
            time.sleep(30)
        return (0, QUOTA_OUT, "")

    monkeypatch.setattr(proc, "probe", fake)
    start = time.monotonic()
    rows = data.lab_quotas("alice")
    assert time.monotonic() - start < 5, "the deadline did not fire"
    assert len(rows) == 4
    assert [row.error for row in rows if row.error] == ["still reading"]


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


def test_the_label_names_the_lab_before_the_filesystem():
    """Cut from the tail, filesystem first took forty labs to three names at 80 columns."""
    label = data._label("/n/holylfs06/LABS/lab_one", "lab_one")
    assert label.startswith("lab_one@")


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


async def test_refresh_all_skips_a_side_column_that_is_not_on_screen(monkeypatch):
    """Forty lookups for a panel nobody can see is pure load on a shared service."""
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
        assert not app.query_one("#storage").display
        await pilot.press("R")
        await pilot.pause(0.3)
        assert storage_calls == []


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


def _painted(app):
    """Return every character the compositor drew, for asserting on the frame."""
    return "".join(
        segment.text for strip in app.screen._compositor.render_strips() for segment in strip
    )
