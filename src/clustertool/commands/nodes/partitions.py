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
      - Find GPU partitions (filter by name, e.g. --filter kempner).

    \b
    Inputs:
      -f, --filter  Only show rows containing this text (the header is kept).
    """
    tool = site.tool("partitions")
    if not name_filter:
        process.passthrough([tool], f"'{tool}' failed")
        return
    code, out, err = process.probe([tool])
    if code:
        raise click.ClickException(f"'{tool}' failed: {err.strip() or code}")
    lines = out.splitlines()
    if lines:
        click.echo(lines[0])
        for line in lines[1:]:
            if name_filter in line:
                click.echo(line)
