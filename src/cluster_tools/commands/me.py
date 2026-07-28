"""me command."""

import os

import click

from cluster_tools import slurm
from cluster_tools.grouping import keywords


@keywords("dashboard", "home", "overview", "status", "mine", "summary")
@click.command("me")
@click.option("-u", "--user", default=None, help="Show another user instead of yourself.")
def me(user: str | None) -> None:
    """Show a personal overview: your jobs, GPUs in use, and fairshare standing.

    A one-screen summary of your cluster life, so you do not have to run squeue
    and sshare separately.

    \b
    Use cases:
      - Start the day with one command that shows where you stand.
      - Check your running and pending jobs and fairshare at a glance.

    \b
    Inputs:
      -u, --user  Show this user instead of the current one.
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

    click.echo("")
    click.echo("Storage: clustertools storage quota <filesystem>  (e.g. netscratch, home)")
