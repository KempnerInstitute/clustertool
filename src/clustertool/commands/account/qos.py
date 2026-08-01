"""account qos command."""

import click

from clustertool import process
from clustertool.grouping import keywords

_FORMAT = "Name%28,Priority,MaxWall,MaxTRESPU%-32,MaxTRES%18,GrpTRES%18"
_LONG_FORMAT = (
    "Name%28,Priority,MaxWall,GrpTRES%18,MaxTRES%18,MaxTRESPU%-32,"
    "MaxJobsPU,MaxSubmitPU,Flags%20,Preempt%18,UsageFactor"
)


@keywords("quality", "cap", "ceiling", "tier")
@click.command("qos")
@click.option(
    "-f", "--filter", "name_filter", default=None, help="Only show rows containing this text."
)
@click.option(
    "-l",
    "--long",
    "long_format",
    is_flag=True,
    help="Show the full field set (MaxJobsPU, MaxSubmitPU, Flags, Preempt, UsageFactor).",
)
def qos(name_filter: str | None, long_format: bool) -> None:
    """List QoS definitions and their limits (via sacctmgr).

    Shows each QoS with its priority, max wall time, and TRES limits (including
    the per-user and total GPU caps). With --long, add the job-count, submit,
    Flags, Preempt, and UsageFactor columns.

    \b
    Use cases:
      - See the GPU cap and priority of a partition's QoS.
      - Inspect preemption and flags with --long.

    \b
    Inputs:
      -f, --filter  Only show rows containing this text (the header is kept).
      -l, --long    Show the full field set instead of the compact one.
    """
    cmd = ["sacctmgr", "show", "qos", "format=" + (_LONG_FORMAT if long_format else _FORMAT)]
    if not name_filter:
        process.passthrough(cmd, "'sacctmgr show qos' failed")
        return
    code, out, err = process.probe(cmd)
    if code:
        raise click.ClickException(f"'sacctmgr show qos' failed: {err.strip() or code}")
    for i, line in enumerate(out.splitlines()):
        if i < 2 or name_filter.lower() in line.lower():
            click.echo(line)
