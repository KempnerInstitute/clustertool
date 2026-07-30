"""storage quota command."""

import os

import click

from cluster_tools import process
from cluster_tools.grouping import keywords
from cluster_tools.storage import quota_cmd


@keywords("disk", "space", "limit")
@click.command("quota")
@click.argument("path")
@click.option("-g", "--group", help="Group/lab name for the quota lookup.")
@click.option("-u", "--user", help="User name for the quota lookup.")
@click.option("-v", "--verbose", is_flag=True, help="Show the underlying quota command.")
def quota(path: str, group: str | None, user: str | None, verbose: bool) -> None:
    """Show a storage quota on any filesystem (via the FASRC quota tool).

    Reports quota and usage for PATH, which selects the filesystem: VAST
    (/n/netscratch), Lustre (/n/holylfs06, /n/holystore01, ...), home, and so on.
    Use --group for a lab's quota or --user for a user's; with neither, the quota
    tool infers from the path. A bare name like 'holylfs06' becomes
    '/n/holylfs06', and 'home' resolves to your home directory.

    \b
    Use cases:
      - Lab quota on scratch: storage quota netscratch -g kempner_dev
      - Lab quota on Lustre: storage quota holylfs06 -g kempner_dev
      - Your own usage: storage quota holystore01 -u $USER

    \b
    Inputs:
      PATH           Filesystem path, or a bare name that becomes /n/<name>.
      -g, --group    Group/lab name for the lookup.
      -u, --user     User name for the lookup.
      -v, --verbose  Show the underlying quota command.
    """
    if group and user:
        raise click.ClickException("give at most one of --group / --user")
    if path == "home":
        target = os.path.expanduser("~")
    else:
        target = path if path.startswith("/") else f"/n/{path}"
    code = process.stream(quota_cmd(target, group=group, user=user, verbose=verbose))
    if code:
        raise SystemExit(code)
