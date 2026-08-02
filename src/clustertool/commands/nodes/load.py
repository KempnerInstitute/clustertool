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
      -f, --filter  Only show rows containing this text, matched without regard
                    to case (the header is kept).
    """
    tool = site.tool("node_load")
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
