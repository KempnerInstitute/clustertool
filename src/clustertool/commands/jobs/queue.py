"""jobs queue command."""

import click

from clustertool import completion, process, site
from clustertool.grouping import ToolCommand, keywords


@keywords("pending", "waiting", "backlog", "showq")
@click.command("queue", cls=ToolCommand, tool_key="queue")
@click.argument("partition", shell_complete=completion.complete_partitions)
def queue(partition: str) -> None:
    """Show a partition's pending jobs in priority order (via showq).

    Lists who is waiting and where you sit, ordered by priority. Unlike
    'jobs list' (your jobs) this is the whole partition's pending queue.

    \b
    Use cases:
      - See how far back your pending job is in a partition.
      - Gauge contention before submitting.

    \b
    Inputs:
      PARTITION  Slurm partition name (e.g. kempner_h100).
    """
    code = process.stream([site.tool("queue"), "-o", "-p", partition])
    if code:
        raise SystemExit(code)
