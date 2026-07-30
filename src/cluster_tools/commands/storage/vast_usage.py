"""storage vast-usage command."""

import click

from cluster_tools import process
from cluster_tools.grouping import keywords


@keywords("disk", "space", "du", "consumption")
@click.command("vast-usage")
@click.argument("path")
@click.option("-g", "--group", required=True, help="Unix group to break usage down by.")
def vast_usage(path: str, group: str) -> None:
    """Show per-user usage for a group on a VAST filesystem (via the quota tool).

    Lists how much each member of GROUP is using under PATH. Works on VAST
    filesystems such as /n/netscratch. A bare name like 'netscratch' becomes
    '/n/netscratch'.

    \b
    Use cases:
      - See who in a lab is filling a shared scratch or VAST allocation.

    \b
    Inputs:
      PATH         Filesystem path, or a bare name that becomes /n/<name>.
      -g, --group  Unix group to break usage down by.
    """
    target = path if path.startswith("/") else f"/n/{path}"
    code = process.stream(["quota", "--group-user-usage", group, target])
    if code:
        raise SystemExit(code)
