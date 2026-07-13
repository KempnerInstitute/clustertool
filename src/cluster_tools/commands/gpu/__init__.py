"""GPU usage commands."""

import click

from cluster_tools.commands.gpu.avail import avail
from cluster_tools.commands.gpu.monitor_job import monitor_job
from cluster_tools.commands.gpu.monitor_partition import monitor_partition
from cluster_tools.commands.gpu.nvtop import nvtop
from cluster_tools.commands.gpu.usage import usage


@click.group()
def gpu() -> None:
    """Inspect GPU usage on the cluster."""


gpu.add_command(usage)
gpu.add_command(avail)
gpu.add_command(monitor_partition)
gpu.add_command(monitor_job)
gpu.add_command(nvtop)
