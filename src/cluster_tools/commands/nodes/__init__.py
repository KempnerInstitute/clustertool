"""Node commands."""

import click

from cluster_tools.commands.nodes.list import list_nodes


@click.group()
def nodes() -> None:
    """Inspect cluster nodes."""


nodes.add_command(list_nodes)
