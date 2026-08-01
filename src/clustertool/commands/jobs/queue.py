"""jobs queue command."""

import click

from clustertool import completion, process, site, slurm
from clustertool.grouping import ToolCommand, keywords


@keywords("pending", "waiting", "backlog", "showq")
@click.command("queue", cls=ToolCommand, tool_key="queue")
@click.argument("partition", shell_complete=completion.complete_partitions)
def queue(partition: str) -> None:
    """Show a partition's whole queue, waiting jobs in priority order (via showq).

    Lists the partition's active, waiting, and blocked jobs, with the waiting
    ones ordered by priority so you can see where you sit. Unlike 'jobs list',
    which shows your own jobs, this covers everyone's. A partition the cluster
    does not have is an error, since showq reports it as an empty queue.

    \b
    Use cases:
      - See how far back your pending job is in a partition.
      - Gauge contention before submitting.

    \b
    Inputs:
      PARTITION  Slurm partition name.
    """
    if not slurm.partition_exists(partition):
        raise click.ClickException(f"partition '{partition}' does not exist")
    process.passthrough(
        [site.tool("queue"), "-o", "-p", partition],
        f"'{site.tool('queue')}' failed for partition {partition}",
    )
