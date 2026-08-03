"""Painted-screen tests for the me dashboard.

The rest of the suite asserts on what a widget returns from render, which is why
a missing border and an invisible focus ring both shipped green. These compare
the painted screen, so a layout regression shows up as a diff.
"""

import datetime

from clustertool.tui.app import MeApp
from clustertool.tui.data import Identity, JobRow, QuotaRow, StorageInfo
from clustertool.tui.panels.jobs import JobsPanel
from clustertool.tui.panels.storage import StoragePanel

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


STORAGE = StorageInfo(
    home=QuotaRow("home", "76G", "95G", "80%", "12%"),
    labs=[
        QuotaRow("nayar_lab@fastfs", "-", "-", "-", error="quota timed out"),
        QuotaRow("nayar_lab@labstore", "4.0Ti", "4.0Ti", "100%", "30%"),
        QuotaRow("nayar_lab@fastfs02", "39.05T", "40T", "98%", "40%"),
        QuotaRow("rivera_lab@scratch", "18T", "20T", "90%", "12%"),
        QuotaRow("okonkwo_project_beta@fastfs02", "45.51T", "75T", "79%", "99%"),
        QuotaRow("a_lab_with_a_very_long_name@labstore", "1.0Ti", "4.0Ti", "25%", "5%"),
        QuotaRow("tanaka_lab@scratch", "212.6G", "-", "-", "-"),
    ],
    mine=[QuotaRow("fastfs02", "50.43T", "0k", "-", "-")],
)


async def _storage(pilot, info):
    pilot.app.query_one(StoragePanel).show(info)
    await pilot.pause()


def test_storage_loaded(snap_compare):
    assert snap_compare(
        _app(),
        terminal_size=(120, 30),
        run_before=lambda pilot: _storage(pilot, STORAGE),
    )


def test_storage_still_reading(snap_compare):
    """The panel before its first result, which is what a cold six-second load shows."""
    assert snap_compare(_app(), terminal_size=(120, 30))


def test_storage_stale_after_a_failed_read(snap_compare):
    async def stale(pilot):
        panel = pilot.app.query_one(StoragePanel)
        panel.show(STORAGE)
        await pilot.pause()
        panel.fail("quota service did not answer")
        await pilot.pause()

    assert snap_compare(_app(), terminal_size=(120, 30), run_before=stale)


def test_storage_with_no_lab_directories(snap_compare):
    empty = StorageInfo(home=QuotaRow("home", "1G", "95G", "1%"), labs=[], mine=[])
    assert snap_compare(
        _app(),
        terminal_size=(120, 30),
        run_before=lambda pilot: _storage(pilot, empty),
    )


def test_storage_at_80_columns(snap_compare):
    """The narrowest terminal that shows the panel at all, where rows are 22 wide.

    The bar survives even here: dropping it needs a row under 17, which the panel's
    own width floor rules out, so that branch is a backstop rather than a layout
    the app can reach.
    """
    assert snap_compare(
        _app(),
        terminal_size=(80, 24),
        run_before=lambda pilot: _storage(pilot, STORAGE),
    )


def test_storage_while_reading(snap_compare):
    """The frame during a load, which is what the panel shows for two to six seconds.

    Entered through begin_read rather than left to a stub, because every other
    snapshot builds the app with the timer off, so no worker ever runs and this
    frame went unrendered while a Textual loading flag was deleting the border.
    """

    async def reading(pilot):
        panel = pilot.app.query_one(StoragePanel)
        panel.show(STORAGE)
        await pilot.pause()
        panel.begin_read()
        await pilot.pause()

    assert snap_compare(_app(), terminal_size=(120, 30), run_before=reading)
