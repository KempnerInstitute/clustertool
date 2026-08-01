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
    """Show per-node load and free CPU/GPU/memory (via the site tool).

    \b
    Use cases:
      - Find nodes with spare capacity.
      - Check how busy a specific node is.

    \b
    Inputs:
      -f, --filter  Only show rows containing this text (the header is kept).
    """
    tool = site.tool("node_load")
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
