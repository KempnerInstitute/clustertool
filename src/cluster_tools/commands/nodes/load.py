"""nodes load command."""

import click

from cluster_tools import process
from cluster_tools.grouping import keywords


@keywords("busy", "free", "cpu", "memory")
@click.command("load")
@click.option(
    "-f", "--filter", "name_filter", default=None, help="Only show rows containing this text."
)
def load(name_filter: str | None) -> None:
    """Show per-node load and free CPU/GPU/memory (via lsload).

    \b
    Use cases:
      - Find nodes with spare capacity.
      - Check how busy a specific node is.

    \b
    Inputs:
      -f, --filter  Only show rows containing this text (the header is kept).
    """
    if not name_filter:
        code = process.stream(["lsload"])
        if code:
            raise SystemExit(code)
        return
    lines = process.run(["lsload"]).splitlines()
    if lines:
        click.echo(lines[0])
        for line in lines[1:]:
            if name_filter in line:
                click.echo(line)
