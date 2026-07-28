"""account qos command."""

import click

from cluster_tools import process

_FORMAT = "Name%28,Priority,MaxWall,MaxTRESPU%22,MaxTRES%18,GrpTRES%18"


@click.command("qos")
@click.option(
    "-f", "--filter", "name_filter", default=None, help="Only show rows containing this text."
)
def qos(name_filter: str | None) -> None:
    """List QOS definitions and their limits (via sacctmgr).

    Shows each QOS with its priority, max wall time, and TRES limits (including
    the per-user and total GPU caps).

    \b
    Use cases:
      - See the GPU cap and priority of a partition's QOS.

    \b
    Inputs:
      -f, --filter  Only show rows containing this text (the header is kept).
    """
    cmd = ["sacctmgr", "show", "qos", "format=" + _FORMAT]
    if not name_filter:
        code = process.stream(cmd)
        if code:
            raise SystemExit(code)
        return
    for i, line in enumerate(process.run(cmd).splitlines()):
        if i < 2 or name_filter.lower() in line.lower():
            click.echo(line)
