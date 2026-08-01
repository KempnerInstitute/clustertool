"""Storage quota command construction and multi-target lab quota helpers."""

import glob
import os
import re
from collections.abc import Callable

from clustertool import process, site

_UNIT = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}


def parse_du_top(output: str, root: str, top_n: int) -> list[tuple[int, str]]:
    """Return the top-N largest (size_bytes, path) subdirectories from du output."""
    entries = []
    for line in output.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        size, path = int(parts[0]), parts[1]
        if path.rstrip("/") == root.rstrip("/"):
            continue
        entries.append((size, path))
    entries.sort(reverse=True)
    return entries[:top_n]


def humanize_bytes(num: int) -> str:
    """Format a byte count as a short human-readable size."""
    size = float(num)
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024 or unit == "T":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}P"


def quota_cmd(
    path: str, group: str | None = None, user: str | None = None, verbose: bool = False
) -> list[str]:
    """Return the FASRC quota command for a path, optionally by group or user."""
    cmd = [site.tool("quota")]
    if group:
        cmd += ["-g", group]
    if user:
        cmd += ["-u", user]
    if verbose:
        cmd.append("-v")
    cmd.append(path)
    return cmd


def _to_bytes(text: str) -> float:
    """Parse a size like '1.5T' or '200Gi' into bytes; 0 when unparseable."""
    match = re.match(r"([0-9.]+)\s*([KkMGTP]?)", text.rstrip("i"))
    if not match:
        return 0.0
    return float(match.group(1)) * _UNIT.get(match.group(2).upper(), 1)


def _count(text: str) -> float:
    """Parse a plain count; 0 when unparseable."""
    try:
        return float(text)
    except ValueError:
        return 0.0


def _percent(value: float, cap: float, cap_text: str) -> str:
    """Return 'NN%' of value against cap, or '-' when the cap is unset or zero."""
    if cap_text in ("-", "0", "") or cap == 0:
        return "-"
    return f"{100 * value / cap:.0f}%"


def parse_quota_row(output: str) -> tuple[str, str, str, str] | None:
    """Parse FASRC quota output into (used, quota, disk_percent, files_percent).

    Handles the 5-column NFS shape and the 9-column Lustre shape, reading the
    first data row (a line for a filesystem path). Returns None when none is
    present.

    The Lustre shape carries a soft quota and a hard limit. The effective limit
    is the soft quota when it is set, and the hard limit otherwise.
    """
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 5 or not fields[0].startswith("/"):
            continue
        used = fields[1]
        if len(fields) >= 9:
            quota = _effective_limit(fields[2], fields[3])
            files, files_quota = fields[5], _effective_limit(fields[6], fields[7])
        else:
            quota = fields[2]
            files, files_quota = fields[3], fields[4]
        disk_pct = _percent(_to_bytes(used), _to_bytes(quota), quota)
        files_pct = _percent(_count(files), _count(files_quota), files_quota)
        return used, quota, disk_pct, files_pct
    return None


def _effective_limit(soft: str, hard: str) -> str:
    """Return the limit actually in force, preferring a set soft quota."""
    return hard if _to_bytes(soft) == 0 and _to_bytes(hard) > 0 else soft


def percent_value(text: str) -> float:
    """Return a percent string like '90%' as a float, or -1 for '-' or unparseable."""
    try:
        return float(text.rstrip("%"))
    except ValueError:
        return -1.0


def user_groups(user: str) -> list[str]:
    """Return a user's Unix group names (via id -nG)."""
    return process.run(["id", "-nG", user]).split()


def lab_targets(
    groups: list[str], roots: list[str], is_dir: Callable[[str], bool] = os.path.isdir
) -> list[tuple[str, str]]:
    """Return (path, group) for each of the user's lab dirs found under the roots.

    Slurm priority-tier pseudo-groups are skipped, and each path appears once.
    """
    prefix = site.slurm_group_prefix()
    targets = []
    seen = set()
    for group in groups:
        if group.startswith(prefix):
            continue
        for root in roots:
            path = f"{root}/{group}"
            if path not in seen and is_dir(path):
                seen.add(path)
                targets.append((path, group))
    return targets


def fleet_targets(root: str, keyword: str) -> list[tuple[str, str]]:
    """Return (path, name) for each directory matching keyword* under root, sorted."""
    targets = []
    for path in sorted(glob.glob(f"{root}/{keyword}*")):
        if os.path.isdir(path):
            targets.append((path, os.path.basename(path)))
    return targets
