"""me command."""

import os
import pwd
import sys

import click

from clustertool import site, slurm, storage
from clustertool.grouping import keywords


def _caller() -> str:
    """Return the caller's username from the uid.

    A uid with no passwd entry raises, which happens in a container or during a
    directory outage, so it is reported as something the caller can act on
    rather than as a traceback.
    """
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError as exc:
        raise click.UsageError(f"could not determine who you are ({exc}); pass -u USER") from exc


def _wants_dashboard(user: str | None, plain: bool, access: bool) -> bool:
    """Return True when this invocation asks for the interactive dashboard.

    The dashboard covers the caller only, so naming another user falls back to
    the one-shot summary, as does asking for the access map or redirecting the
    output. Both streams must be a terminal: with stdout a terminal and stdin
    not, the app draws but no keypress can reach it, leaving something that
    cannot be quit. A dumb terminal cannot render it at all.

    Whether the optional extra is installed is settled by importing it, not
    asked here, so the check and the import cannot disagree.
    """
    if plain or user or access:
        return False
    if os.environ.get("TERM", "") in ("", "dumb"):
        return False
    return sys.stdout.isatty() and sys.stdin.isatty()


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
        click.echo("Where you can submit (account -> partition -> QoS)")
        acct_w = max(len("ACCOUNT"), max(len(a) for a, _, _ in associations))
        part_w = max(len("PARTITION"), max(len(p or "(any)") for _, p, _ in associations))
        click.echo(f"  {'ACCOUNT':<{acct_w}}  {'PARTITION':<{part_w}}  QOS")
        for account, partition, qos in sorted(associations):
            click.echo(f"  {account:<{acct_w}}  {(partition or '(any)'):<{part_w}}  {qos or '-'}")
    prefix = site.slurm_group_prefix()
    tiers = sorted(group for group in storage.user_groups(user) if group.startswith(prefix))
    if tiers:
        click.echo("")
        click.echo("Slurm priority tiers")
        for tier in tiers:
            click.echo(f"  {tier}")


@keywords("dashboard", "home", "overview", "status", "mine", "access")
@click.command("me")
@click.option("-u", "--user", default=None, help="Show another user instead of yourself.")
@click.option("--plain", is_flag=True, help="Print the one-shot summary instead of the dashboard.")
@click.option(
    "-a", "--access", is_flag=True, help="Also show what you can access: accounts, partitions, QoS."
)
@click.option(
    "-i",
    "--interval",
    type=click.FloatRange(min=2),
    default=5.0,
    show_default=True,
    help="Seconds between dashboard job refreshes.",
)
@click.option(
    "-d",
    "--days",
    type=click.IntRange(min=1),
    default=7,
    show_default=True,
    help="Days of finished jobs the dashboard standing panel covers.",
)
def me(user: str | None, plain: bool, access: bool, interval: float, days: int) -> None:
    """Show a personal overview: your jobs, GPUs in use, and fairshare standing.

    A one-screen summary of your cluster life, so you do not have to run squeue
    and sshare separately. With --access, also show the accounts, partitions, and
    QoS you may submit under, and your Slurm priority tiers.

    \b
    Use cases:
      - Start the day with one command that shows where you stand.
      - See what you can access with --access before submitting a job.

    \b
    Inputs:
      -u, --user      Show this user instead of the current one.
      --plain         Print the one-shot summary instead of the dashboard.
      -a, --access    Also show your accounts, submission map, and priority tiers.
      -i, --interval  Seconds between dashboard job refreshes.
      -d, --days      Days of finished jobs the standing panel covers.

    Run in a terminal with no other flags, this opens an interactive dashboard
    where the optional tui extra is installed. Naming a user, asking for the
    access map, or redirecting the output prints the one-shot summary instead.
    The interval has a floor of two seconds, since every tick is a query on the
    controller and r refreshes on demand; a wide window slows the standing panel,
    which reads that many days of accounting.
    """
    if _wants_dashboard(user, plain, access):
        try:
            from clustertool.tui.app import run
        except ImportError:
            pass
        else:
            run(interval=interval, days=days)
            return
    user = user or _caller()
    click.echo(f"clustertool overview for {user}")

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
        click.echo(f"  ... and {len(jobs) - 10} more (clustertool jobs list)")

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
    click.echo("Storage: clustertool storage quota --all  (or <filesystem>, e.g. netscratch)")
