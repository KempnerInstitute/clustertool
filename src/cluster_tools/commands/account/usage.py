"""account usage command."""

import datetime
import os

import click

from cluster_tools import completion, process
from cluster_tools.grouping import keywords


@keywords("hours", "spend", "cost")
@click.command("usage")
@click.argument("account", required=False, shell_complete=completion.complete_accounts)
@click.option(
    "-d", "--days", type=int, default=30, show_default=True, help="Period length in days."
)
@click.option("-u", "--user", default=None, help="User to report (default: you).")
@click.option(
    "--efficiency",
    is_flag=True,
    help="Show efficiency histograms (seff-account) instead of usage hours.",
)
def usage(account: str | None, days: int, user: str | None, efficiency: bool) -> None:
    """Report cumulative CPU/GPU/TRES-hours for an account or user (via stotal).

    Sums usage over the last --days. With --efficiency, show the seff-account
    efficiency summary instead. With an ACCOUNT, report that account (querying
    accounts you do not belong to needs operator rights); otherwise report you.

    \b
    Use cases:
      - See how many GPU-hours a lab or member used this month.
      - Check the efficiency of a lab's jobs over a period.

    \b
    Inputs:
      ACCOUNT       Slurm account. Omit to report yourself.
      -d, --days    Period length in days (default 30).
      -u, --user    User to report (default: current user).
      --efficiency  Use seff-account (efficiency) instead of stotal (hours).
    """
    if account and user:
        raise click.UsageError("Give an ACCOUNT or --user, not both.")
    scope = ["-A", account] if account else ["-u", user or os.environ.get("USER", "")]
    end_dt = datetime.datetime.now()
    start = (end_dt - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    end = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
    if efficiency:
        cmd = ["seff-account", *scope, "-S", start, "-E", end]
    else:
        cmd = ["stotal", *scope, "-S", start, "-E", end, "-d"]
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
