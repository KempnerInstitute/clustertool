"""Shell-completion setup and dynamic value completion for clustertools."""

import os
from pathlib import Path

from cluster_tools.process import CommandError
from cluster_tools.process import run as _run

SHELLS = ("bash", "zsh", "fish")

_ENV = "_CLUSTERTOOLS_COMPLETE"


def eval_line(shell: str) -> str:
    """Return the startup line that enables clustertools completion for a shell."""
    if shell == "fish":
        return f"{_ENV}=fish_source clustertools | source"
    return f'eval "$({_ENV}={shell}_source clustertools)"'


def rc_path(shell: str) -> Path:
    """Return the startup file the completion line belongs in for a shell."""
    home = Path.home()
    if shell == "zsh":
        return home / ".zshrc"
    if shell == "fish":
        return home / ".config" / "fish" / "config.fish"
    return home / ".bashrc"


def detect_shell() -> str | None:
    """Return the shell basename from $SHELL if it is one we support."""
    name = os.path.basename(os.environ.get("SHELL", ""))
    return name if name in SHELLS else None


def ensure_line(path: Path, line: str) -> bool:
    """Append line to path if absent; return True if added, False if already present."""
    existing = path.read_text() if path.exists() else ""
    if line in existing.splitlines():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "\n" if existing and not existing.endswith("\n") else ""
    with path.open("a") as handle:
        handle.write(f"{prefix}{line}\n")
    return True


def _safe(cmd: list[str]) -> str:
    """Run a query for completion, returning empty output on any failure."""
    try:
        return _run(cmd)
    except (CommandError, OSError):
        return ""


def complete_job_ids(ctx, param, incomplete):
    """Complete with the current user's Slurm job IDs."""
    user = os.environ.get("USER", "")
    if not user:
        return []
    out = _safe(["squeue", "-h", "-u", user, "-o", "%i"])
    return [job for job in out.split() if job.startswith(incomplete)]


def complete_partitions(ctx, param, incomplete):
    """Complete with partition names from sinfo."""
    out = _safe(["sinfo", "-h", "-o", "%P"])
    names = sorted({part.rstrip("*") for part in out.split() if part})
    return [part for part in names if part.startswith(incomplete)]


def complete_accounts(ctx, param, incomplete):
    """Complete with the current user's Slurm accounts."""
    user = os.environ.get("USER", "")
    if not user:
        return []
    out = _safe(["sacctmgr", "-nP", "show", "assoc", f"user={user}", "format=Account"])
    names = sorted({line.strip() for line in out.splitlines() if line.strip()})
    return [name for name in names if name.startswith(incomplete)]
