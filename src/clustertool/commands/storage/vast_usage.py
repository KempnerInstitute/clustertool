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
    target = path if path.startswith("/") else f"{site.path_prefix()}/{path}"
    tool = site.tool("quota")
    if process.stream([tool, "--group-user-usage", group, target]):
        raise click.ClickException(f"'{tool} --group-user-usage' failed for {group} on {target}")
