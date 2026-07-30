"""storage scratch command."""

import os

import click

from cluster_tools import process, site
from cluster_tools.grouping import keywords


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
    scratch_dir = site.scratch_path()
    path = path or os.environ.get("SCRATCH") or scratch_dir
    target = path if path.startswith("/") else f"{site.path_prefix()}/{path}"
    code = process.stream(["quota", target])
    click.echo()
    click.echo(
        f"Note: files under {scratch_dir} are deleted after {site.scratch_purge_days()} days "
        "and are not backed up."
    )
    if code:
        raise SystemExit(code)
