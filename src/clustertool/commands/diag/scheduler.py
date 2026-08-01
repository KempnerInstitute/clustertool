"""diag scheduler command."""

import click

from clustertool import process
from clustertool.grouping import keywords


@keywords("sdiag", "backfill", "slurm", "health")
@click.command("scheduler")
def scheduler() -> None:
    """Show Slurm scheduler diagnostics (via sdiag).

    Reports scheduling cycle times, backfill statistics, and queue depth, which
    help explain why the queue feels slow.

    \b
    Use cases:
      - Check scheduler health and backfill activity when jobs are slow to start.
    """
    code = process.stream(["sdiag"])
    if code:
        raise SystemExit(code)
