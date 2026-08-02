"""Painted-screen tests for the me dashboard.

The rest of the suite asserts on what a widget returns from render, which is why
a missing border and an invisible focus ring both shipped green. These compare
the painted screen, so a layout regression shows up as a diff.
"""

import datetime

from clustertool.tui.app import MeApp
from clustertool.tui.data import Identity

FIXED_CLOCK = datetime.datetime(2026, 8, 2, 14, 32)
WHO = Identity("alice", "A Name", "node01", "Example HPC")


def _app():
    return MeApp(identity=WHO, clock=lambda: FIXED_CLOCK)


def test_shell_at_80x24(snap_compare):
    assert snap_compare(_app(), terminal_size=(80, 24))


def test_shell_at_100x30(snap_compare):
    assert snap_compare(_app(), terminal_size=(100, 30))


def test_shell_with_focus_moved(snap_compare):
    assert snap_compare(_app(), terminal_size=(100, 24), press=["tab"])


def test_help_overlay(snap_compare):
    assert snap_compare(_app(), terminal_size=(100, 24), press=["question_mark"])
