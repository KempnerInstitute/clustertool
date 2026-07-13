"""Diagnostic commands."""

import click

from cluster_tools.commands.diag.ib import ib
from cluster_tools.commands.diag.nccl import nccl
from cluster_tools.commands.diag.nvlink import nvlink


@click.group()
def diag() -> None:
    """Run cluster diagnostics."""


diag.add_command(ib)
diag.add_command(nccl)
diag.add_command(nvlink)
