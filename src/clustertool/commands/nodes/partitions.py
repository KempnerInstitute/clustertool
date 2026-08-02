"""nodes partitions command."""

import click

from clustertool import process, site
from clustertool.grouping import ToolCommand, keywords


@keywords("queues", "partition", "cores", "spart")
@click.command("partitions", cls=ToolCommand, tool_key="partitions")
@click.option(
    "-f", "--filter", "name_filter", default=None, help="Only show rows containing this text."
)
def partitions(name_filter: str | None) -> None:
    """List partitions with cores, GPUs, memory, and time limits (via the site tool).

    \b
    Use cases:
      - See which partitions exist and how big their nodes are.
      - Find GPU partitions by name with --filter.

    \b
    Inputs:
      -f, --filter  Only show rows containing this text, matched without regard
                    to case (the header is kept).
    """
    tool = site.tool("partitions")
    if not name_filter:
        process.passthrough([tool], f"'{tool}' failed")
        return
    code, out, err = process.probe([tool])
    if code:
        raise click.ClickException(f"'{tool}' failed: {err.strip() or code}")
    if err.strip():
        click.echo(err.rstrip(), err=True)
    lines = out.splitlines()
    if not lines:
        return
    click.echo(lines[0])
    wanted = name_filter.lower()
    matched = [line for line in lines[1:] if wanted in line.lower()]
    for line in matched:
        click.echo(line)
    if not matched:
        click.echo(
            f"  (no row contains {name_filter!r}; {len(lines) - 1} row(s) before the filter)"
        )
