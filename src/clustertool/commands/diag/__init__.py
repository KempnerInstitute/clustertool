"""Diagnostic commands."""

import click

from clustertool.commands.diag.gpu_health import gpu_health
from clustertool.commands.diag.ib import ib
from clustertool.commands.diag.ib_affinity import ib_affinity
from clustertool.commands.diag.ib_counters import ib_counters
from clustertool.commands.diag.ib_snapshot import ib_snapshot
from clustertool.commands.diag.ib_verify import ib_verify
from clustertool.commands.diag.io_probe import io_probe
from clustertool.commands.diag.nccl import nccl
from clustertool.commands.diag.nvlink import nvlink
from clustertool.commands.diag.scheduler import scheduler
from clustertool.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def diag() -> None:
    """Cluster diagnostics and benchmarks."""


diag.add_command(gpu_health)
diag.add_command(ib)
diag.add_command(ib_affinity)
diag.add_command(ib_counters)
diag.add_command(ib_snapshot)
diag.add_command(ib_verify)
diag.add_command(io_probe)
diag.add_command(nccl)
diag.add_command(nvlink)
diag.add_command(scheduler)
