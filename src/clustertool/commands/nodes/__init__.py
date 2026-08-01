"""Node commands."""

import click

from clustertool.commands.nodes.down import down
from clustertool.commands.nodes.frag import frag
from clustertool.commands.nodes.list import list_nodes
from clustertool.commands.nodes.load import load
from clustertool.commands.nodes.partitions import partitions
from clustertool.commands.nodes.reservations import reservations
from clustertool.commands.nodes.resume import resume
from clustertool.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def nodes() -> None:
    """Node and partition status, load, and reservations."""


nodes.add_command(list_nodes)
nodes.add_command(partitions)
nodes.add_command(down)
nodes.add_command(frag)
nodes.add_command(load)
nodes.add_command(reservations)
nodes.add_command(resume)
