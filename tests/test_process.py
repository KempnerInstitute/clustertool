"""Tests for the process helpers."""

import os
import sys

from clustertool import process


def test_child_env_strips_our_own_virtualenv(monkeypatch, tmp_path):
    own = tmp_path / "ourvenv"
    (own / "bin").mkdir(parents=True)
    monkeypatch.setattr(process.sys, "prefix", str(own))
    monkeypatch.setattr(process.sys, "base_prefix", "/usr")
    monkeypatch.setenv("VIRTUAL_ENV", str(own))
    monkeypatch.setenv("PATH", os.pathsep.join([str(own / "bin"), "/usr/bin", "/bin"]))
    env = process._child_env()
    assert "VIRTUAL_ENV" not in env
    parts = env["PATH"].split(os.pathsep)
    assert str(own / "bin") not in parts
    assert "/usr/bin" in parts


def test_child_env_keeps_the_users_own_virtualenv(monkeypatch, tmp_path):
    """A wrapped install must not strip the torch env diag nccl asks the user for."""
    own = tmp_path / "toolvenv"
    theirs = tmp_path / "uservenv"
    for path in (own, theirs):
        (path / "bin").mkdir(parents=True)
    monkeypatch.setattr(process.sys, "prefix", str(own))
    monkeypatch.setattr(process.sys, "base_prefix", "/usr")
    monkeypatch.setenv("VIRTUAL_ENV", str(theirs))
    monkeypatch.setenv("PATH", os.pathsep.join([str(theirs / "bin"), str(own / "bin"), "/usr/bin"]))
    env = process._child_env()
    assert env["VIRTUAL_ENV"] == str(theirs)
    parts = env["PATH"].split(os.pathsep)
    assert str(theirs / "bin") in parts
    assert str(own / "bin") not in parts


def test_child_env_outside_a_virtualenv_changes_nothing(monkeypatch):
    monkeypatch.setattr(process.sys, "prefix", "/usr")
    monkeypatch.setattr(process.sys, "base_prefix", "/usr")
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/bin"]))
    env = process._child_env()
    assert env["PATH"] == os.pathsep.join(["/usr/bin", "/bin"])


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
