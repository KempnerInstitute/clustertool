"""Painted-screen tests for the me dashboard.

The rest of the suite asserts on what a widget returns from render, which is why
a missing border and an invisible focus ring both shipped green. These compare
the painted screen, so a layout regression shows up as a diff.
"""

import datetime

from clustertool.tui.app import MeApp
from clustertool.tui.data import Identity, JobRow
from clustertool.tui.panels.jobs import JobsPanel

FIXED_CLOCK = datetime.datetime(2026, 8, 2, 14, 32)
WHO = Identity("alice", "A Name", "node01", "Example HPC")


def _app():
    return MeApp(identity=WHO, clock=lambda: FIXED_CLOCK, interval=0)


def test_shell_at_80x24(snap_compare):
    assert snap_compare(_app(), terminal_size=(80, 24))


def test_shell_at_100x30(snap_compare):
    assert snap_compare(_app(), terminal_size=(100, 30))


def test_shell_with_focus_moved(snap_compare):
    assert snap_compare(_app(), terminal_size=(100, 24), press=["tab"])


def test_help_overlay(snap_compare):
    assert snap_compare(_app(), terminal_size=(100, 24), press=["question_mark"])


SAMPLE = [
    JobRow(
        "111",
        "R",
        "RUNNING",
        "kempner_h100",
        4,
        "2:14:00",
        "None",
        "gpu8a[15-16]",
        2,
        "cpu=96,mem=1440G,gres/gpu=4",
    ),
    JobRow(
        "222",
        "R",
        "RUNNING",
        "sapphire",
        0,
        "6:02:11",
        "None",
        "holy7c04309",
        1,
        "cpu=8,mem=64G",
    ),
    JobRow(
        "333_[0-7]",
        "PD",
        "PENDING",
        "kempner_h100,kempner_requeue",
        4,
        "0:00",
        "ReqNodeNotAvail, UnavailableNodes:holygpu8a[11101-11408]",
        "",
        1,
        "cpu=96,gres/gpu=4",
    ),
]


async def _show(pilot, rows):
    pilot.app.query_one(JobsPanel).show(rows)
    await pilot.pause()


def test_jobs_populated(snap_compare):
    assert snap_compare(
        _app(),
        terminal_size=(100, 26),
        run_before=lambda pilot: _show(pilot, SAMPLE),
    )


def test_jobs_empty(snap_compare):
    assert snap_compare(
        _app(),
        terminal_size=(100, 26),
        run_before=lambda pilot: _show(pilot, []),
    )


def test_jobs_at_80_columns(snap_compare):
    assert snap_compare(
        _app(),
        terminal_size=(80, 24),
        run_before=lambda pilot: _show(pilot, SAMPLE),
    )


def test_jobs_pending_row_selected(snap_compare):
    """The waiting line and the elided cells are only on screen for a pending job."""

    async def pending(pilot):
        await _show(pilot, SAMPLE)
        await pilot.press("down", "down")
        await pilot.pause()

    assert snap_compare(_app(), terminal_size=(100, 26), run_before=pending)


def test_jobs_at_70x16(snap_compare):
    """The size where the detail pane was squeezed off screen entirely."""
    assert snap_compare(
        _app(),
        terminal_size=(70, 16),
        run_before=lambda pilot: _show(pilot, SAMPLE),
    )


def test_jobs_stale_after_a_failed_refresh(snap_compare):
    async def stale(pilot):
        panel = pilot.app.query_one(JobsPanel)
        panel.show(SAMPLE)
        await pilot.pause()
        panel.fail("controller busy")
        await pilot.pause()

    assert snap_compare(_app(), terminal_size=(100, 26), run_before=stale)
