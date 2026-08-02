"""diag scheduler command."""

import click

from clustertool import process, site
from clustertool.grouping import ToolCommand, keywords


@keywords("sdiag", "backfill", "slurm", "health")
@click.command("scheduler", cls=ToolCommand, tool_key="sdiag")
@click.pass_context
def scheduler(ctx: click.Context) -> None:
    """Show Slurm scheduler diagnostics (via sdiag).

    Reports scheduling cycle times, backfill statistics, and queue depth, which
    help explain why the queue feels slow. The binary comes from [tools].sdiag in
    the site config.

    \b
    Exit codes:
      0  the diagnostics were read
      3  sdiag could not be run, or reported an error
    2 is unused throughout the diagnostics, since click exits 2 on a usage error.

    \b
    Use cases:
      - Check scheduler health and backfill activity when jobs are slow to start.
    """
    code = process.stream([site.tool("sdiag")])
    if code == process.SIGPIPE_EXIT:
        raise SystemExit(process.SIGPIPE_EXIT)
    if code:
        ctx.exit(3)
