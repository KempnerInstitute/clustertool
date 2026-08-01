"""storage lfs-inodes command."""

import os

import click

from clustertool import process, site
from clustertool.grouping import ToolCommand, keywords


@keywords("files", "count", "lustre")
@click.command("lfs-inodes", cls=ToolCommand, tool_key="lfs")
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
    target = path if path.startswith("/") else f"{site.path_prefix()}/{path}"
    if not os.path.exists(target):
        raise click.ClickException(f"path not found: {target}")
    lfs = site.tool("lfs")
    if process.stream([lfs, "df", "-i", target]):
        raise click.ClickException(f"'{lfs} df' failed for {target}")
