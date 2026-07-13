"""Job commands."""

import click

from cluster_tools.commands.jobs.stats import stats


@click.group()
def jobs() -> None:
    """Inspect Slurm jobs."""


jobs.add_command(stats)
