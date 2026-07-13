"""Tests for the process helpers."""

import os

from cluster_tools import process


def test_child_env_strips_virtualenv(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/venv")
    monkeypatch.setenv("PATH", os.pathsep.join(["/tmp/venv/bin", "/usr/bin", "/bin"]))
    env = process._child_env()
    assert "VIRTUAL_ENV" not in env
    parts = env["PATH"].split(os.pathsep)
    assert "/tmp/venv/bin" not in parts
    assert "/usr/bin" in parts
