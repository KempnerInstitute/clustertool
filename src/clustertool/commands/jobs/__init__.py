"""Job commands."""

import click

from clustertool.commands.jobs.bestpartition import best_partition
from clustertool.commands.jobs.cancel import cancel
from clustertool.commands.jobs.debug import debug
from clustertool.commands.jobs.failures import failures
from clustertool.commands.jobs.history import history
from clustertool.commands.jobs.hold import hold
from clustertool.commands.jobs.list import list_jobs
from clustertool.commands.jobs.log import log
from clustertool.commands.jobs.new import new
from clustertool.commands.jobs.priorities import priorities
from clustertool.commands.jobs.queue import queue
from clustertool.commands.jobs.release import release
from clustertool.commands.jobs.requeue import requeue
from clustertool.commands.jobs.scope import scope
from clustertool.commands.jobs.script import script
from clustertool.commands.jobs.setpriority import set_priority
from clustertool.commands.jobs.show import show
from clustertool.commands.jobs.stats import stats
from clustertool.commands.jobs.submit import submit
from clustertool.commands.jobs.top import top
from clustertool.commands.jobs.violators import violators
from clustertool.commands.jobs.waittimes import wait_times
from clustertool.commands.jobs.why import why
from clustertool.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def jobs() -> None:
    """Inspect, submit, and control Slurm jobs."""


jobs.aliases = {"setprio": "set-priority"}


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
jobs.add_command(set_priority)
jobs.add_command(submit)
jobs.add_command(new)
jobs.add_command(debug)
jobs.add_command(failures)
jobs.add_command(wait_times)
jobs.add_command(best_partition)
