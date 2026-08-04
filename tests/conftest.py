"""Shared fixtures."""

import signal

import pytest

from clustertool import site


@pytest.fixture(autouse=True)
def keep_sigpipe_ignored():
    """Leave SIGPIPE as pytest set it, whatever a test does to it.

    The CLI entry point restores the default disposition on purpose, so that piping
    a command into head exits quietly the way squeue does. A test that runs the entry
    point leaves that disposition behind for the whole session, and pytest is then
    killed with 141 rather than raising when its own output pipe breaks, which
    reports as a failure with no failing test.
    """
    original = signal.getsignal(signal.SIGPIPE)
    yield
    signal.signal(signal.SIGPIPE, original)


@pytest.fixture(autouse=True)
def site_tools_present(request, monkeypatch):
    """Report every site tool as installed unless a test opts out.

    Commands built on ToolCommand refuse to run when their host tool is missing,
    so without this the suite passes on a cluster login node and fails on a bare
    runner. Mark a test with real_site_tools to exercise the real PATH lookup.
    """
    if "real_site_tools" in request.keywords:
        return
    monkeypatch.setattr(site, "tool_available", lambda key: True)
