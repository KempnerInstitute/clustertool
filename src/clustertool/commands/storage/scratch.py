"""storage scratch command."""

import os

import click

from clustertool import process, site
from clustertool.grouping import ToolCommand, keywords


@keywords("temp", "purge", "netscratch")
@click.command("scratch", cls=ToolCommand, tool_key="quota")
@click.argument("path", required=False)
def scratch(path: str | None) -> None:
    """Show networked scratch usage and the purge policy (via the quota tool).

    Reports quota and usage for your scratch path, then restates the site's purge
    policy: how long files survive there, and that scratch is not backed up. The
    path and the purge age both come from [storage] in the site config. PATH
    defaults to $SCRATCH, then the configured scratch path; a bare name is
    completed with [storage].path_prefix.

    \b
    Use cases:
      - Check how full your lab's scratch allocation is.
      - Remember the auto-deletion age before staging data there.

    \b
    Inputs:
      PATH  Scratch path (default: $SCRATCH, else the site's scratch path).
    """
    scratch_dir = site.scratch_path()
    path = path or os.environ.get("SCRATCH") or scratch_dir
    target = path if path.startswith("/") else f"{site.path_prefix()}/{path}"
    code = process.stream([site.tool("quota"), target])
    if code:
        raise click.ClickException(f"quota lookup failed for {target}")
    click.echo()
    if target == scratch_dir or target.startswith(scratch_dir.rstrip("/") + "/"):
        click.echo(
            f"Note: files under {scratch_dir} are deleted after {site.scratch_purge_days()} days "
            "and are not backed up."
        )
    else:
        click.echo(
            f"Note: {target} is not under the site scratch path ({scratch_dir}), so the "
            f"{site.scratch_purge_days()}-day purge does not apply to it."
        )
