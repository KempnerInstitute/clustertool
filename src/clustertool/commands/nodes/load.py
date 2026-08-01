"""nodes load command."""

import click

from clustertool import process, site
from clustertool.grouping import ToolCommand, keywords


@keywords("busy", "free", "cpu", "memory")
@click.command("load", cls=ToolCommand, tool_key="node_load")
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
        if process.stream([site.tool("node_load")]):
            raise click.ClickException(f"'{site.tool('node_load')}' failed")
        return
    lines = process.run([site.tool("node_load")]).splitlines()
    if lines:
        click.echo(lines[0])
        for line in lines[1:]:
            if name_filter in line:
                click.echo(line)
