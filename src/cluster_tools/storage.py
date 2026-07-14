"""Storage quota command construction."""


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
