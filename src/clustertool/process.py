"""Subprocess helpers for running system commands."""

import os
import subprocess


class CommandError(RuntimeError):
    """Raised when a required command is missing or cannot be run."""


def _child_env() -> dict[str, str]:
    """Return a child environment with this tool's virtualenv removed."""
    env = os.environ.copy()
    venv = env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    if venv:
        bin_dir = os.path.join(venv, "bin")
        parts = [p for p in env.get("PATH", "").split(os.pathsep) if p and p != bin_dir]
        env["PATH"] = os.pathsep.join(parts)
    return env


def run(cmd: list[str], input_text: str | None = None) -> str:
    """Run a command and return its captured stdout."""
    kwargs = {"capture_output": True, "text": True, "check": False, "env": _child_env()}
    if input_text is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = input_text
    try:
        result = subprocess.run(cmd, **kwargs)
    except FileNotFoundError as exc:
        raise CommandError(f"'{cmd[0]}' not found on this host") from exc
    return result.stdout


def probe(cmd: list[str], timeout: float | None = None) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr).

    Unlike run(), this exposes the exit status instead of raising, for callers
    that treat a nonzero exit as data. A missing binary yields (127, "", "") and
    a timeout yields (124, "", ""), following the shell conventions for those.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=_child_env(),
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    except FileNotFoundError:
        return (127, "", "")
    except subprocess.TimeoutExpired:
        return (124, "", "")
    return (result.returncode, result.stdout, result.stderr)


def succeeds(cmd: list[str]) -> bool:
    """Return True if the command runs and exits 0 (output discarded)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=_child_env(),
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def stream(cmd: list[str], extra_env: dict[str, str] | None = None) -> int:
    """Run a command with inherited stdio and return its exit code."""
    env = _child_env()
    if extra_env:
        env.update(extra_env)
    try:
        return subprocess.run(cmd, check=False, env=env).returncode
    except FileNotFoundError as exc:
        raise CommandError(f"'{cmd[0]}' not found on this host") from exc
