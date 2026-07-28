"""Job commands."""

import click

from cluster_tools.commands.jobs.cancel import cancel
from cluster_tools.commands.jobs.history import history
from cluster_tools.commands.jobs.hold import hold
from cluster_tools.commands.jobs.list import list_jobs
from cluster_tools.commands.jobs.log import log
from cluster_tools.commands.jobs.priorities import priorities
from cluster_tools.commands.jobs.queue import queue
from cluster_tools.commands.jobs.release import release
from cluster_tools.commands.jobs.requeue import requeue
from cluster_tools.commands.jobs.scope import scope
from cluster_tools.commands.jobs.script import script
from cluster_tools.commands.jobs.setprio import setprio
from cluster_tools.commands.jobs.show import show
from cluster_tools.commands.jobs.stats import stats
from cluster_tools.commands.jobs.submit import submit
from cluster_tools.commands.jobs.top import top
from cluster_tools.commands.jobs.violators import violators
from cluster_tools.commands.jobs.why import why
from cluster_tools.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def jobs() -> None:
    """Inspect, submit, and control Slurm jobs."""


jobs.add_command(list_jobs)
jobs.add_command(queue)
jobs.add_command(show)
jobs.add_command(why)
jobs.add_command(top)
jobs.add_command(stats)
jobs.add_command(scope)
jobs.add_command(history)
jobs.add_command(log)
jobs.add_command(script)
jobs.add_command(priorities)
jobs.add_command(violators)
jobs.add_command(cancel)
jobs.add_command(hold)
jobs.add_command(release)
jobs.add_command(requeue)
jobs.add_command(setprio)
jobs.add_command(submit)
