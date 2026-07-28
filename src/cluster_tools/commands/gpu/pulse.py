"""gpu pulse command."""

import sys

import click

from cluster_tools import process
from cluster_tools.grouping import keywords


@keywords("dcgm", "realtime", "monitor", "htop")
@click.command(
    "pulse",
    context_settings={"ignore_unknown_options": True, "help_option_names": []},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED, metavar="[ARG]...")
def pulse(args: tuple[str, ...]) -> None:
    """Live GPU utilization dashboard, via the bundled kempnerpulse tool.

    All arguments are forwarded to kempnerpulse unchanged, so its full option
    set is available. Run 'clustertools gpu pulse --help' for the complete list
    (that help is produced by kempnerpulse itself).

    \b
    Most useful:
      gpu pulse                 live fleet dashboard (dcgm backend)
      gpu pulse --once          render one snapshot and exit
      gpu pulse --focus-gpu 0   start focused on a single GPU
      gpu pulse --gpus 0,1      limit to specific GPUs

    Run this on a GPU node (for example inside a Slurm job). For completed-job
    efficiency use 'jobs scope' instead.
    """
    code = process.stream([sys.executable, "-m", "kempnerpulse", *args])
    if code:
        raise SystemExit(code)
