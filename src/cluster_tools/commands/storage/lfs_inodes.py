"""storage lfs-inodes command."""

import click

from cluster_tools import process
from cluster_tools.grouping import keywords


@keywords("files", "count", "lustre")
@click.command("lfs-inodes")
@click.argument("path")
def lfs_inodes(path: str) -> None:
    """Show inode capacity and usage for a Lustre filesystem (via lfs df -i).

    PATH must be on a Lustre filesystem (for example /n/holylfs06 or
    /n/holystore01). A bare name like 'holylfs06' becomes '/n/holylfs06'.

    \b
    Use cases:
      - Check whether a Lustre filesystem is running low on inodes.

    \b
    Inputs:
      PATH  A Lustre path, or a bare name that becomes /n/<name>.
    """
    target = path if path.startswith("/") else f"/n/{path}"
    code = process.stream(["lfs", "df", "-i", target])
    if code:
        raise SystemExit(code)
