"""Job commands."""

import click

from cluster_tools.commands.jobs.cancel import cancel
from cluster_tools.commands.jobs.history import history
from cluster_tools.commands.jobs.list import list_jobs
from cluster_tools.commands.jobs.scope import scope
from cluster_tools.commands.jobs.show import show
from cluster_tools.commands.jobs.stats import stats
from cluster_tools.commands.jobs.submit import submit
from cluster_tools.commands.jobs.violators import violators
from cluster_tools.commands.jobs.why import why


@click.group()
def jobs() -> None:
    """Inspect Slurm jobs."""


jobs.add_command(list_jobs)
jobs.add_command(show)
jobs.add_command(why)
jobs.add_command(stats)
jobs.add_command(scope)
jobs.add_command(history)
jobs.add_command(violators)
jobs.add_command(cancel)
jobs.add_command(submit)
