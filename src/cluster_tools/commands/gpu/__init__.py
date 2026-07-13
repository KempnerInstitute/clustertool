"""GPU usage commands."""

import click

from cluster_tools.commands.gpu.avail import avail
from cluster_tools.commands.gpu.lab_util import lab_util
from cluster_tools.commands.gpu.labs_util import labs_util
from cluster_tools.commands.gpu.monitor_job import monitor_job
from cluster_tools.commands.gpu.monitor_partition import monitor_partition


@click.group()
def gpu() -> None:
    """Inspect GPU usage on the cluster."""


gpu.add_command(labs_util)
gpu.add_command(lab_util)
gpu.add_command(avail)
gpu.add_command(monitor_partition)
gpu.add_command(monitor_job)
