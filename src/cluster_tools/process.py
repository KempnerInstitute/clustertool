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


def stream(cmd: list[str]) -> int:
    """Run a command with inherited stdio and return its exit code."""
    try:
        return subprocess.run(cmd, check=False, env=_child_env()).returncode
    except FileNotFoundError as exc:
        raise CommandError(f"'{cmd[0]}' not found on this host") from exc
