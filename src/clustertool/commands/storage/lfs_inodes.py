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

    PATH must be on a Lustre filesystem. A bare name is completed with
    [storage].path_prefix from the site config, so 'holylfs06' becomes
    '/n/holylfs06' with the packaged Kempner profile.

    \b
    Use cases:
      - Check whether a Lustre filesystem is running low on inodes.

    \b
    Inputs:
      PATH  A Lustre path, or a bare name the site prefix completes.
    """
    target = path if path.startswith("/") else f"{site.path_prefix()}/{path}"
    if not os.path.exists(target):
        raise click.ClickException(f"path not found: {target}")
    lfs = site.tool("lfs")
    if process.stream([lfs, "df", "-i", target]):
        raise click.ClickException(f"'{lfs} df' failed for {target}")
