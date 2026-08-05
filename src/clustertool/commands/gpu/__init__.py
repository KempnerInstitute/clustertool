"""GPU usage commands."""

import click

from clustertool.commands.gpu.avail import avail
from clustertool.commands.gpu.monitor_job import monitor_job
from clustertool.commands.gpu.monitor_partition import monitor_partition
from clustertool.commands.gpu.nvtop import nvtop
from clustertool.commands.gpu.pulse import pulse
from clustertool.commands.gpu.session import session
from clustertool.commands.gpu.status import status
from clustertool.commands.gpu.usage import usage
from clustertool.commands.gpu.util import util
from clustertool.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def gpu() -> None:
    """GPU usage, availability, sessions, and monitoring."""


gpu.add_command(usage)
gpu.add_command(util)
gpu.add_command(status)
gpu.add_command(avail)
gpu.add_command(session)
gpu.add_command(monitor_partition)
gpu.add_command(monitor_job)
gpu.add_command(nvtop)
gpu.add_command(pulse)
