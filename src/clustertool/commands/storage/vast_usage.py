"""storage vast-usage command."""

import click

from clustertool import process, site
from clustertool.grouping import ToolCommand, keywords


@keywords("disk", "space", "du", "consumption")
@click.command("vast-usage", cls=ToolCommand, tool_key="quota")
@click.argument("path")
@click.option("-g", "--group", required=True, help="Unix group to break usage down by.")
def vast_usage(path: str, group: str) -> None:
    """Show per-user usage for a group on a VAST filesystem (via the quota tool).

    PATH selects the filesystem, and the figures cover the whole mountpoint
    rather than only what sits under PATH. Each user's number is their total on
    that filesystem, not their usage under GROUP alone; GROUP selects whose names
    to list. Works on VAST filesystems. A bare name is completed with
    [storage].path_prefix from the site config, so 'netscratch' becomes
    '/n/netscratch' with the packaged Kempner profile.

    \b
    Use cases:
      - See who in a lab is filling a shared scratch or VAST allocation.

    \b
    Inputs:
      PATH         Filesystem path, or a bare name the site prefix completes.
      -g, --group  Unix group to break usage down by.
    """
    target = path if path.startswith("/") else f"{site.path_prefix()}/{path}"
    tool = site.tool("quota")
    process.passthrough(
        [tool, "--group-user-usage", group, target],
        f"'{tool} --group-user-usage' failed for {group} on {target}",
    )
