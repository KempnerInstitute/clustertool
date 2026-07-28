"""GPU usage commands."""

import click

from cluster_tools.commands.gpu.avail import avail
from cluster_tools.commands.gpu.monitor_job import monitor_job
from cluster_tools.commands.gpu.monitor_partition import monitor_partition
from cluster_tools.commands.gpu.nvtop import nvtop
from cluster_tools.commands.gpu.pulse import pulse
from cluster_tools.commands.gpu.session import session
from cluster_tools.commands.gpu.status import status
from cluster_tools.commands.gpu.usage import usage
from cluster_tools.commands.gpu.util import util
from cluster_tools.grouping import SectionedGroup


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
