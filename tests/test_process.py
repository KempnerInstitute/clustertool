"""Tests for the process helpers."""

import os
import sys

from clustertool import process


def test_child_env_strips_virtualenv(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/venv")
    monkeypatch.setenv("PATH", os.pathsep.join(["/tmp/venv/bin", "/usr/bin", "/bin"]))
    env = process._child_env()
    assert "VIRTUAL_ENV" not in env
    parts = env["PATH"].split(os.pathsep)
    assert "/tmp/venv/bin" not in parts
    assert "/usr/bin" in parts


def test_probe_returns_code_and_output():
    code, out, err = process.probe([sys.executable, "-c", "import sys; print('hi'); sys.exit(3)"])
    assert code == 3
    assert "hi" in out


def test_probe_missing_binary_returns_127():
    code, out, err = process.probe(["definitely-not-a-real-binary-xyz"])
    assert code == 127
    assert out == ""


def test_probe_timeout_returns_124():
    code, out, err = process.probe(
        [sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2
    )
    assert code == 124
    assert out == ""
