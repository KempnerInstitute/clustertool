"""jobs list command."""

import os

import click

from cluster_tools import process


@click.command("list")
@click.option("-u", "--user", default=None, help="User whose jobs to list (default: you).")
@click.option(
    "-t",
    "--state",
    type=click.Choice(["running", "pending"]),
    default=None,
    help="Only jobs in this state.",
)
@click.option("-p", "--partition", default=None, help="Only jobs in this partition.")
@click.option("-A", "--account", default=None, help="Only jobs in this account.")
def list_jobs(
    user: str | None, state: str | None, partition: str | None, account: str | None
) -> None:
    """List your queued and running jobs (via squeue).

    \b
    Use cases:
      - See what you have running and pending right now.
      - Check why a job is pending (the NODELIST(REASON) column).

    \b
    Inputs:
      -u, --user       User whose jobs to list (default: current user).
      -t, --state      Limit to running or pending jobs.
      -p, --partition  Limit to one partition.
      -A, --account    Limit to one account.
    """
    cmd = ["squeue", "-u", user or os.environ.get("USER", "")]
    if state:
        cmd += ["-t", state.upper()]
    if partition:
        cmd += ["-p", partition]
    if account:
        cmd += ["-A", account]
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
