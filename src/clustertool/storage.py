"""Storage quota command construction and multi-target lab quota helpers."""

import glob
import os
import re
from collections.abc import Callable

from clustertool import process, site

_UNIT = {
    "": 1,
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
    "P": 1024**5,
    "E": 1024**6,
    "Z": 1024**7,
    "Y": 1024**8,
}


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
    """Parse a size like '1.5T', '200Gi' or '20k' into bytes; 0 when unparseable."""
    match = re.match(r"([0-9.]+)\s*([KkMmGgTtPpEeZzYy]?)", text.rstrip("i"))
    if not match:
        return 0.0
    return float(match.group(1)) * _UNIT.get(match.group(2).upper(), 1)


def _count(text: str) -> float | None:
    """Parse a plain count; None when it cannot be read.

    None keeps a suffixed or malformed count out of the percentage, so the cell
    reads as unknown rather than as zero usage. lfs stars the used cell of the
    inode group as well as the block group, per man lfs-quota, so the star is
    stripped: an over-quota inode count is the one case the column exists for.
    """
    try:
        return float(text.rstrip("*"))
    except ValueError:
        return None


def _percent(value: float, cap: float, cap_text: str) -> str:
    """Return 'NN%' of value against cap, or '-' when the cap is unset or zero."""
    if cap_text in ("-", "0", "") or cap == 0:
        return "-"
    return f"{100 * value / cap:.0f}%"


_QUOTA_VALUE = re.compile(r"^(?:-|\*?[0-9.]+[KkMmGgTtPpEeZzYy]?i?\*?)$")
"""A used, quota or limit cell. lfs marks a value that is over quota with a star."""


def _is_quota_values(fields: list[str]) -> bool:
    """Return True if the line holds a quota row's numbers rather than prose.

    lfs prints notes of its own between rows, such as a default-quota message,
    and joining one to a wrapped mount point would invent a row.
    """
    return bool(fields) and _QUOTA_VALUE.match(fields[0]) is not None


def _data_rows(output: str) -> list[list[str]]:
    """Return the quota data rows, rejoining a filesystem name that wrapped its line.

    lfs quota puts the mount point on a line of its own once it outgrows the
    column, leaving the numbers on the next line.
    """
    rows: list[list[str]] = []
    pending = ""
    for line in output.splitlines():
        fields = line.split()
        if not fields:
            continue
        if pending and _is_quota_values(fields):
            rows.append([pending, *fields])
            pending = ""
            continue
        pending = ""
        if len(fields) == 1 and fields[0].startswith("/"):
            pending = fields[0]
        elif fields[0].startswith("/"):
            rows.append(fields)
    return rows


def parse_quota_row(output: str) -> tuple[str, str, str, str] | None:
    """Parse quota-tool output into (used, quota, disk_percent, files_percent).

    Reads the data rows, each a line starting with a filesystem path in either the
    5-column VAST shape or the 9-column Lustre shape. Rows of any other width are
    ignored, so the df table the quota tool prints for a filesystem it does not
    track yields None rather than a misread quota.

    The tool prints one block per matching quota record, and a group can have more
    than one on the same mount point. The row reporting the most usage wins, since
    that is the record actually constraining the group; taking whichever came
    first would report an unused record as the group's usage.

    The Lustre shape carries a soft quota and a hard limit. The effective limit is
    the soft quota when it is set, and the hard limit otherwise.
    """
    best: tuple[str, str, str, str] | None = None
    best_used = -1.0
    for fields in _data_rows(output):
        if len(fields) != 5 and len(fields) < 9:
            continue
        used = fields[1]
        if len(fields) >= 9:
            quota = _effective_limit(fields[2], fields[3])
            files, files_quota = fields[5], _effective_limit(fields[6], fields[7])
        else:
            quota = fields[2]
            files, files_quota = fields[3], fields[4]
        used_bytes = _to_bytes(used)
        if used_bytes <= best_used:
            continue
        best_used = used_bytes
        count, cap = _count(files), _count(files_quota)
        files_pct = "-" if count is None or cap is None else _percent(count, cap, files_quota)
        best = (used, quota, _percent(used_bytes, _to_bytes(quota), quota), files_pct)
    return best


def _effective_limit(soft: str, hard: str) -> str:
    """Return the limit actually in force, preferring a set soft quota."""
    return hard if _to_bytes(soft) == 0 and _to_bytes(hard) > 0 else soft


def lustre_ost_count(path: str) -> int:
    """Return how many OSTs back a Lustre path, or 0 when that cannot be determined.

    A stripe count above this is accepted by lfs but silently clamped, so it is
    worth knowing before setting one. Returns 0 rather than raising, since the
    count is only used to sanity-check a request.
    """
    code, out, _ = process.probe([site.tool("lfs"), "osts", path])
    if code != 0:
        return 0
    return sum(1 for line in out.splitlines() if "_UUID" in line)


def mount_point(path: str, mounts: str | None = None) -> tuple[str, str]:
    """Return the (mount point, filesystem type) a path sits on, or ('', '').

    Read from mountinfo rather than by trying a tool and seeing whether it works,
    so a Lustre-only query is not sent to an NFS path in the first place. The
    longest matching mount point wins, since mounts nest.
    """
    try:
        if mounts is None:
            with open("/proc/self/mountinfo", encoding="utf-8", errors="replace") as handle:
                mounts = handle.read()
    except OSError:
        return "", ""
    target = os.path.realpath(path)
    best, kind = "", ""
    for line in mounts.splitlines():
        head, _, tail = line.partition(" - ")
        fields = head.split()
        if len(fields) < 5:
            continue
        point = fields[4]
        if (target == point or target.startswith(point.rstrip("/") + "/")) and len(point) > len(
            best
        ):
            best, kind = point, tail.split()[0] if tail.split() else ""
    return best, kind


def used_bytes(text: str) -> float:
    """Return a rendered usage figure as bytes, for ordering rows of equal percent."""
    return _to_bytes(text)


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
    """Return (path, name) for each directory named keyword* directly under root.

    The keyword is matched literally, so a glob character or a path separator in it
    cannot widen the search beyond one level of root.
    """
    targets = []
    for path in sorted(glob.glob(f"{root}/{glob.escape(keyword)}*")):
        if os.path.isdir(path):
            targets.append((path, os.path.basename(path)))
    return targets
