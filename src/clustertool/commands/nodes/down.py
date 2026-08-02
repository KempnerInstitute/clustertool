"""nodes down command."""

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords


@keywords("broken", "offline", "dead")
@click.command("down")
@click.option(
    "-p",
    "--partition",
    default=None,
    help="Limit to one partition.",
    shell_complete=completion.complete_partitions,
)
def down(partition: str | None) -> None:
    """List the nodes sinfo -R reports, with the scheduler's reason.

    man sinfo scopes -R to nodes that are down, drained, draining or failing, so
    this is not every node that cannot take work: a reserved node, one in
    maintenance, one powered down, and one whose base state is idle but which is
    not responding are all missing from it. Reads nothing and changes nothing.

    \b
    Use cases:
      - See which nodes are out and why before blaming your job.
      - Spot a partition losing capacity to failures.

    \b
    Inputs:
      -p, --partition  Limit to one partition.
    """
    cmd = ["sinfo", "-R", "-o", "%60E %12u %19H %N"]
    if partition:
        if not slurm.partition_exists(partition):
            raise click.ClickException(f"partition '{partition}' does not exist")
        cmd += ["-p", partition]
    process.passthrough(cmd, "'sinfo -R' failed")
