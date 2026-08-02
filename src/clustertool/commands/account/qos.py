"""account qos command."""

import click

from clustertool import process
from clustertool.grouping import keywords

_FORMAT = "Name%28,Priority,MaxWall,MaxTRESPU%-32,MaxTRESPA%18,MaxTRES%18,GrpTRES%18,MaxJobsPU"
"""Every limit qos create and qos modify can set, so the two views agree."""
_LONG_FORMAT = (
    "Name%28,Priority,MaxWall,GrpTRES%18,MaxTRES%18,MaxTRESPU%-32,MaxTRESPA%18,"
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
    help="Also show MaxSubmitPU, Flags, Preempt and UsageFactor.",
)
def qos(name_filter: str | None, long_format: bool) -> None:
    """List QoS definitions and their limits (via sacctmgr).

    Shows each QoS with its priority, max wall time, and TRES limits: the
    per-user, per-account, per-job, and total GPU caps, so every limit qos create
    and qos modify can set is readable here. With --long, add the job-count,
    submit, Flags, Preempt, and UsageFactor columns.

    \b
    Use cases:
      - See the GPU cap and priority of a partition's QoS.
      - Inspect preemption and flags with --long.

    \b
    Inputs:
      -f, --filter  Only show rows containing this text (the header is kept).
      -l, --long    Also show MaxSubmitPU, Flags, Preempt and UsageFactor.
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
