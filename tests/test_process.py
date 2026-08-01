"""Tests for the process helpers."""

import os
import subprocess
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


def test_stream_reports_a_closed_pipe_as_sigpipe(tmp_path):
    """A reader closing the pipe, as head does, must be distinguishable from a failure."""
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import signal, sys\n"
        "from clustertool import process\n"
        "signal.signal(signal.SIGPIPE, signal.SIG_DFL)\n"
        "sys.exit(process.stream(['seq', '2000000']))\n"
    )
    piped = subprocess.Popen(
        [sys.executable, str(runner)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    piped.stdout.readline()
    piped.stdout.close()
    assert piped.wait() == process.SIGPIPE_EXIT


def test_sigpipe_exit_matches_the_shell_convention():
    """128 + SIGPIPE(13), the code a shell reports for a child killed by a closed pipe."""
    assert process.SIGPIPE_EXIT == 141
