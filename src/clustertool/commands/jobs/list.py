"""jobs list command."""

import os
import pwd

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords


@keywords("mine", "myjobs", "running", "queued")
@click.command("list")
@click.option("-u", "--user", default=None, help="User whose jobs to list (default: you).")
@click.option(
    "-t",
    "--state",
    type=click.Choice(["running", "pending"]),
    default=None,
    help="Only jobs in this state.",
)
@click.option(
    "-p",
    "--partition",
    default=None,
    help="Only jobs in this partition.",
    shell_complete=completion.complete_partitions,
)
@click.option(
    "-A",
    "--account",
    default=None,
    help="Only jobs in this account.",
    shell_complete=completion.complete_accounts,
)
@click.option("--start", is_flag=True, help="Show estimated start time for pending jobs.")
def list_jobs(
    user: str | None,
    state: str | None,
    partition: str | None,
    account: str | None,
    start: bool,
) -> None:
    """List your queued and running jobs (via squeue).

    A filter that names something the cluster does not have is an error, since
    squeue answers a mistyped user, partition or account with an empty list. A
    filter value is trimmed first, because a stray space passes an account lookup
    and then matches nothing. The default user is the account this process runs
    as, not $USER, which a script can leave stale.

    \b
    Use cases:
      - See what you have running and pending right now.
      - Check why a job is pending (the NODELIST(REASON) column).
      - Estimate when pending jobs will start (--start).

    \b
    Inputs:
      -u, --user       User whose jobs to list (default: you).
      -t, --state      Limit to running or pending jobs.
      -p, --partition  Limit to one partition.
      -A, --account    Limit to one account.
      --start          Show the estimated start time of pending jobs.
    """
    user = user.strip() if user is not None else None
    partition = partition.strip() if partition is not None else None
    account = account.strip() if account is not None else None
    if user is not None and not slurm.user_exists(user):
        raise click.ClickException(f"no such user: {user!r}")
    if partition is not None and not slurm.partition_exists(partition):
        raise click.ClickException(f"partition {partition!r} does not exist")
    if account is not None and not slurm.account_exists(account):
        raise click.ClickException(f"account {account!r} does not exist")
    target = user or pwd.getpwuid(os.getuid()).pw_name
    cmd = ["squeue", "-u", target]
    if state:
        cmd += ["-t", state.upper()]
    if partition:
        cmd += ["-p", partition]
    if account:
        cmd += ["-A", account]
    if start:
        cmd.append("--start")
    process.passthrough(cmd, "'squeue' failed")
