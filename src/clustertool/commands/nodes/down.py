"""nodes down command."""

import click

from clustertool import completion, process, qos
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
    """List nodes not accepting work, with the scheduler's reason (via sinfo).

    Covers down, drained, draining and failing nodes, as sinfo -R reports them.

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
        if not qos.partition_exists(partition):
            raise click.ClickException(f"partition '{partition}' does not exist")
        cmd += ["-p", partition]
    process.passthrough(cmd, "'sinfo -R' failed")
