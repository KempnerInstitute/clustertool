"""GPU usage commands."""

import click

from cluster_tools.commands.gpu.avail import avail
from cluster_tools.commands.gpu.lab_util import lab_util
from cluster_tools.commands.gpu.labs_util import labs_util


@click.group()
def gpu() -> None:
    """Inspect GPU usage on the cluster."""


gpu.add_command(labs_util)
gpu.add_command(lab_util)
gpu.add_command(avail)
