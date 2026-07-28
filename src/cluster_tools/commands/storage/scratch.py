"""storage scratch command."""

import os

import click

from cluster_tools import process
from cluster_tools.grouping import keywords

_PURGE_DAYS = 90


@keywords("temp", "purge", "netscratch")
@click.command("scratch")
@click.argument("path", required=False)
def scratch(path: str | None) -> None:
    """Show networked scratch usage and the purge policy (via the quota tool).

    Reports quota and usage for your netscratch path, and reminds you that files
    on /n/netscratch are deleted after 90 days and are not backed up. PATH
    defaults to $SCRATCH, then /n/netscratch; a bare name becomes /n/<name>.

    \b
    Use cases:
      - Check how full your lab's netscratch allocation is.
      - Remember the 90-day auto-deletion before staging data there.

    \b
    Inputs:
      PATH  Scratch path (default: $SCRATCH, else /n/netscratch).
    """
    path = path or os.environ.get("SCRATCH") or "/n/netscratch"
    target = path if path.startswith("/") else f"/n/{path}"
    code = process.stream(["quota", target])
    click.echo()
    click.echo(
        f"Note: files under /n/netscratch are deleted after {_PURGE_DAYS} days "
        "and are not backed up."
    )
    if code:
        raise SystemExit(code)
