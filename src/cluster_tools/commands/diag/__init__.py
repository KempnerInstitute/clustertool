"""Diagnostic commands."""

import click

from cluster_tools.commands.diag.ib import ib
from cluster_tools.commands.diag.nccl import nccl
from cluster_tools.commands.diag.nvlink import nvlink
from cluster_tools.commands.diag.scheduler import scheduler


@click.group()
def diag() -> None:
    """Cluster diagnostics and benchmarks."""


diag.add_command(ib)
diag.add_command(nccl)
diag.add_command(nvlink)
diag.add_command(scheduler)
