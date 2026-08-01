"""Shared fixtures."""

import pytest

from clustertool import site


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
