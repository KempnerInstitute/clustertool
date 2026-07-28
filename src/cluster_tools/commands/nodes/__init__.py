"""Node commands."""

import click

from cluster_tools.commands.nodes.down import down
from cluster_tools.commands.nodes.list import list_nodes
from cluster_tools.commands.nodes.load import load
from cluster_tools.commands.nodes.partitions import partitions
from cluster_tools.commands.nodes.reservations import reservations
from cluster_tools.commands.nodes.resume import resume


@click.group()
def nodes() -> None:
    """Node and partition status, load, and reservations."""


nodes.add_command(list_nodes)
nodes.add_command(partitions)
nodes.add_command(down)
nodes.add_command(load)
nodes.add_command(reservations)
nodes.add_command(resume)
