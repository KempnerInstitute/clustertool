"""me command."""

import os

import click

from cluster_tools import slurm, storage
from cluster_tools.grouping import keywords


def _show_access(user: str) -> None:
    """Print what a user can access: accounts, submission map, and priority tiers."""
    associations = slurm.user_associations(user)
    default = slurm.default_account(user)
    accounts = sorted({account for account, _, _ in associations})
    if accounts:
        click.echo("")
        click.echo("Accounts (submit with -A <account>)")
        for account in accounts:
            tag = "  (default)" if account == default else ""
            click.echo(f"  {account}{tag}")
    if associations:
        click.echo("")
        click.echo("Where you can submit (account -> partition -> QOS)")
        acct_w = max(len("ACCOUNT"), max(len(a) for a, _, _ in associations))
        part_w = max(len("PARTITION"), max(len(p or "(any)") for _, p, _ in associations))
        click.echo(f"  {'ACCOUNT':<{acct_w}}  {'PARTITION':<{part_w}}  QOS")
        for account, partition, qos in sorted(associations):
            click.echo(f"  {account:<{acct_w}}  {(partition or '(any)'):<{part_w}}  {qos or '-'}")
    tiers = sorted(g for g in storage.user_groups(user) if g.startswith("slurm_group_"))
    if tiers:
        click.echo("")
        click.echo("Slurm priority tiers")
        for tier in tiers:
            click.echo(f"  {tier}")


@keywords("dashboard", "home", "overview", "status", "mine", "access")
@click.command("me")
@click.option("-u", "--user", default=None, help="Show another user instead of yourself.")
@click.option(
    "-a", "--access", is_flag=True, help="Also show what you can access: accounts, partitions, QOS."
)
def me(user: str | None, access: bool) -> None:
    """Show a personal overview: your jobs, GPUs in use, and fairshare standing.

    A one-screen summary of your cluster life, so you do not have to run squeue
    and sshare separately. With --access, also show the accounts, partitions, and
    QOS you may submit under, and your Slurm priority tiers.

    \b
    Use cases:
      - Start the day with one command that shows where you stand.
      - See what you can access with --access before submitting a job.

    \b
    Inputs:
      -u, --user    Show this user instead of the current one.
      -a, --access  Also show your accounts, submission map, and priority tiers.
    """
    user = user or os.environ.get("USER", "")
    if not user:
        raise click.UsageError("Could not determine the user; pass -u USER.")
    click.echo(f"clustertools overview for {user}")

    jobs = slurm.my_jobs(user)
    running = sum(1 for job in jobs if job[1] == "RUNNING")
    pending = sum(1 for job in jobs if job[1] == "PENDING")
    gpus = slurm.user_gpu_count(user)
    click.echo("")
    click.echo(f"Jobs: {running} running, {pending} pending, {gpus} GPU(s) in use")
    for jobid, state, partition, elapsed, reason in jobs[:10]:
        detail = reason if state == "PENDING" and reason not in ("", "None") else elapsed
        click.echo(f"  {jobid:<12} {state:<9} {partition:<16} {detail}")
    if len(jobs) > 10:
        click.echo(f"  ... and {len(jobs) - 10} more (clustertools jobs list)")

    shares = slurm.user_fairshare(user)
    if shares:
        click.echo("")
        click.echo("Fairshare (higher is higher priority)")
        width = max(len(account) for account, _ in shares)
        for account, score in shares:
            click.echo(f"  {account:<{width}}  {score}")

    if access:
        _show_access(user)

    click.echo("")
    click.echo("Storage: clustertools storage quota --all  (or <filesystem>, e.g. netscratch)")
