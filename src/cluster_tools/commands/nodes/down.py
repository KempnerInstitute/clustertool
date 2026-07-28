"""nodes down command."""

import click

from cluster_tools import process


@click.command("down")
@click.option("-p", "--partition", default=None, help="Limit to one partition.")
def down(partition: str | None) -> None:
    """List down and drained nodes with the scheduler's reason (via sinfo).

    \b
    Use cases:
      - See which nodes are out and why before blaming your job.
      - Spot a partition losing capacity to failures.

    \b
    Inputs:
      -p, --partition  Limit to one partition.
    """
    cmd = ["sinfo", "-R"]
    if partition:
        cmd += ["-p", partition]
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
