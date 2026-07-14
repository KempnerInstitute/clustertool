"""Storage quota command construction."""


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
    cmd = ["quota"]
    if group:
        cmd += ["-g", group]
    if user:
        cmd += ["-u", user]
    if verbose:
        cmd.append("-v")
    cmd.append(path)
    return cmd
