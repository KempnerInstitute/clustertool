"""Node commands."""

import click

from cluster_tools.commands.nodes.list import list_nodes
from cluster_tools.commands.nodes.partitions import partitions


@click.group()
def nodes() -> None:
    """Inspect cluster nodes."""


nodes.add_command(list_nodes)
nodes.add_command(partitions)
