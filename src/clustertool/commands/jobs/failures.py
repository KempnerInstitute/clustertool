"""jobs failures command."""

import datetime
import os
from collections import Counter

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords

_FIELDS = "JobIDRaw,User,Account,Partition,State,ExitCode,Elapsed,NodeList,JobName"
_TIME_FMT = "%Y-%m-%dT%H:%M:%S"
_FAILURE = ("failed", "oom", "timeout", "node_fail", "canceled", "preempted")
_CLASSES = (
    ("OUT_OF_MEMORY", "oom"),
    ("TIMEOUT", "timeout"),
    ("NODE_FAIL", "node_fail"),
    ("PREEMPTED", "preempted"),
    ("CANCELLED", "canceled"),
    ("FAILED", "failed"),
    ("COMPLETED", "completed"),
)


def _window(days: int, since: str | None, until: str | None) -> tuple[str, str]:
    if since or until:
        if not (since and until):
            raise click.ClickException("--since and --until must be given together")
        return since, until
    now = datetime.datetime.now()
    return (now - datetime.timedelta(days=days)).strftime(_TIME_FMT), now.strftime(_TIME_FMT)


def _classify(state: str) -> str:
    upper = (state or "").upper()
    for prefix, cls in _CLASSES:
        if upper.startswith(prefix):
            return cls
    if upper.startswith(("RUNNING", "PENDING", "REQUEUED", "SUSPENDED")):
        return "active"
    return "other"


@keywords("failed", "oom", "timeout", "postmortem", "errors")
@click.command("failures")
@click.option("-u", "--user", help="User to report (default: current user).")
@click.option(
    "-A", "--account", shell_complete=completion.complete_accounts, help="Report an account."
)
@click.option(
    "-p", "--partition", shell_complete=completion.complete_partitions, help="Report a partition."
)
@click.option("-d", "--days", type=int, default=7, show_default=True, help="Window length in days.")
@click.option("--since", help="Window start, YYYY-mm-ddTHH:MM:SS (with --until).")
@click.option("--until", help="Window end, YYYY-mm-ddTHH:MM:SS (with --since).")
@click.option("-n", "--top", type=int, default=10, show_default=True, help="Rows per ranking.")
def failures(
    user: str | None,
    account: str | None,
    partition: str | None,
    days: int,
    since: str | None,
    until: str | None,
    top: int,
) -> None:
    """Summarize finished-job failures over a window (via sacct).

    Classifies terminal jobs (completed / failed / oom / timeout / canceled /
    node_fail / preempted), reports the failure rate, and ranks the top exit
    codes, failing job names, failing users, and incident nodes.

    \b
    Use cases:
      - Spot a run of failures and where they cluster.
      - Find nodes causing out-of-memory or node-failure incidents.

    \b
    Inputs:
      -u, --user       User to report (default: current user).
      -A, --account    Report an account (others' need operator rights).
      -p, --partition  Report a partition.
      -d, --days       Window length in days (default 7).
      --since/--until  Explicit window, YYYY-mm-ddTHH:MM:SS.
      -n, --top        Rows to show per ranking (default 10).
    """
    if sum(bool(x) for x in (user, account, partition)) > 1:
        raise click.ClickException("give only one of -u / -A / -p")
    start, end = _window(days, since, until)
    scope_user = None if (account or partition) else (user or os.environ.get("USER", ""))
    rows = slurm.sacct_window_rows(
        _FIELDS, start, end, user=scope_user, account=account, partition=partition
    )

    jobs = []
    malformed = 0
    for row in rows:
        if len(row) < 9 or not row[0].strip().isdigit():
            malformed += 1
            continue
        _, job_user, _account, _partition, state, exit_code, _elapsed, nodelist, name = row[:9]
        jobs.append(
            {
                "user": job_user,
                "exit": exit_code,
                "nodelist": nodelist,
                "name": name,
                "cls": _classify(state),
            }
        )

    counts = Counter(job["cls"] for job in jobs)
    terminal = len(jobs) - counts.get("active", 0)
    noncompleted = terminal - counts.get("completed", 0)
    rate = (100.0 * noncompleted / terminal) if terminal else 0.0
    failing = [job for job in jobs if job["cls"] in _FAILURE]
    exit_codes = Counter(job["exit"] for job in jobs if job["cls"] == "failed")
    names = Counter(job["name"] for job in failing)
    users = Counter(job["user"] for job in failing)
    incident = Counter(job["nodelist"] for job in jobs if job["cls"] in ("node_fail", "oom"))

    click.echo(f"Job failures  ({start} to {end})")
    click.echo()
    click.echo(
        f"  {terminal} terminal job(s), {counts.get('active', 0)} still active, "
        f"{malformed} malformed row(s) skipped"
    )
    by_class = "  ".join(f"{cls}={counts[cls]}" for cls in sorted(counts) if cls != "active")
    if by_class:
        click.echo(f"  by class: {by_class}")
    click.echo(f"  failure rate: {rate:.1f}% of terminal jobs")

    def table(title: str, pairs: list, label: str) -> None:
        if not pairs:
            return
        click.echo()
        click.echo(f"{title}:")
        for value, count in pairs:
            click.echo(f"  {value:<40}{count:>6} {label}")

    table("top exit codes (failed jobs)", exit_codes.most_common(top), "jobs")
    table("top failing job names", names.most_common(top), "jobs")
    table("top failing users", users.most_common(top), "jobs")
    table("nodes with oom / node_fail incidents", incident.most_common(top), "incidents")
