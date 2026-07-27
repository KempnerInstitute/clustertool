"""nodes partitions command."""

import click

from cluster_tools import process


@click.command("partitions")
@click.option(
    "-f", "--filter", "name_filter", default=None, help="Only show rows containing this text."
)
def partitions(name_filter: str | None) -> None:
    """List partitions with cores, GPUs, memory, and time limits (via spart).

    \b
    Use cases:
      - See which partitions exist and how big their nodes are.
      - Find GPU partitions (filter by name, e.g. --filter kempner).

    \b
    Inputs:
      -f, --filter  Only show rows containing this text (the header is kept).
    """
    if not name_filter:
        code = process.stream(["spart"])
        if code:
            raise SystemExit(code)
        return
    lines = process.run(["spart"]).splitlines()
    if lines:
        click.echo(lines[0])
        for line in lines[1:]:
            if name_filter in line:
                click.echo(line)
