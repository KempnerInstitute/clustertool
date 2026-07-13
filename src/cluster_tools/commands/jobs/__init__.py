"""Job commands."""

import click

from cluster_tools.commands.jobs.stats import stats
from cluster_tools.commands.jobs.violators import violators


@click.group()
def jobs() -> None:
    """Inspect Slurm jobs."""


jobs.add_command(stats)
jobs.add_command(violators)
