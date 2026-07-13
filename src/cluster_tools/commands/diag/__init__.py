"""Diagnostic commands."""

import click

from cluster_tools.commands.diag.nccl import nccl


@click.group()
def diag() -> None:
    """Run cluster diagnostics."""


diag.add_command(nccl)
