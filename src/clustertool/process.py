"""Subprocess helpers for running system commands."""

import os
import subprocess
import sys


class CommandError(RuntimeError):
    """Raised when a required command is missing or cannot be run."""


def _child_env() -> dict[str, str]:
    """Return a child environment with this tool's own virtualenv removed.

    The commands run here are Slurm and system binaries, which clustertool's
    interpreter must not shadow. Only the virtualenv clustertool is itself running
    from is removed: a user who activated their own environment keeps it, since a
    wrapped install would otherwise strip exactly the environment the command
    needs, such as the torch env diag nccl asks for.

    SLURM_TIME_FORMAT goes too. Per man sacct it rewrites every timestamp Slurm
    prints, which would silently defeat the parsing the date arithmetic rests on.
    """
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("SLURM_TIME_FORMAT", None)
    if sys.prefix == sys.base_prefix:
        return env
    own = os.path.realpath(sys.prefix)
    declared = env.get("VIRTUAL_ENV")
    if declared and os.path.realpath(declared) == own:
        env.pop("VIRTUAL_ENV", None)
    bin_dir = os.path.join(own, "bin")
    parts = [
        p for p in env.get("PATH", "").split(os.pathsep) if p and os.path.realpath(p) != bin_dir
    ]
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


def probe(
    cmd: list[str], timeout: float | None = None, input_text: str | None = None
) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr).

    Unlike run(), this exposes the exit status instead of raising, for callers
    that treat a nonzero exit as data. A missing binary yields (127, "", "") and
    a timeout yields (124, "", ""), following the shell conventions for those.
    """
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "check": False,
        "env": _child_env(),
        "timeout": timeout,
    }
    if input_text is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = input_text
    try:
        result = subprocess.run(cmd, **kwargs)
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
        code = subprocess.run(cmd, check=False, env=env).returncode
    except FileNotFoundError as exc:
        raise CommandError(f"'{cmd[0]}' not found on this host") from exc
    return code if code >= 0 else 128 - code


SIGPIPE_EXIT = 141
"""Exit code of a child killed by SIGPIPE, which is a reader closing the pipe."""


def passthrough(cmd: list[str], failure: str, extra_env: dict[str, str] | None = None) -> None:
    """Run a command with inherited stdio, raising CommandError if it fails.

    A reader such as head or less closing the pipe kills the child with SIGPIPE,
    which is not a failure, so that case exits with the shell's own code for it
    instead of reporting one.
    """
    code = stream(cmd, extra_env=extra_env)
    if code == SIGPIPE_EXIT:
        raise SystemExit(SIGPIPE_EXIT)
    if code:
        raise CommandError(failure)
