"""jobs wait-times command."""

import datetime
import os

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords

_FIELDS = "JobIDRaw,Partition,QOS,Submit,Start,State,AllocTRES"
_TIME_FMT = "%Y-%m-%dT%H:%M:%S"


def _window(days: int, since: str | None, until: str | None) -> tuple[str, str]:
    if since or until:
        if not (since and until):
            raise click.ClickException("--since and --until must be given together")
        return since, until
    now = datetime.datetime.now()
    return (now - datetime.timedelta(days=days)).strftime(_TIME_FMT), now.strftime(_TIME_FMT)


def _epoch(text: str) -> int:
    return int(datetime.datetime.strptime(text, _TIME_FMT).timestamp())


def _humanize(seconds: int) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    if seconds < 86400:
        return f"{seconds // 3600}h {seconds % 3600 // 60}m"
    return f"{seconds // 86400}d {seconds % 86400 // 3600}h"


def _bucket(gpus: int) -> str:
    if gpus <= 0:
        return "0"
    if gpus == 1:
        return "1"
    if gpus <= 4:
        return "2-4"
    return ">4"


@keywords("wait", "pending", "start", "latency", "backlog")
@click.command("wait-times")
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
def wait_times(
    user: str | None,
    account: str | None,
    partition: str | None,
    days: int,
    since: str | None,
    until: str | None,
) -> None:
    """Show submit-to-start wait time distributions (via sacct).

    Reports the count and p50/p90/max wait, grouped by partition, QoS, and GPU
    count, over the window. sacct keeps no pending-reason history, so this does
    not separate priority wait from resource wait.

    \b
    Use cases:
      - See how long jobs really wait before starting, and where.
      - Compare wait by GPU count to gauge contention for large jobs.

    \b
    Inputs:
      -u, --user       User to report (default: current user).
      -A, --account    Report an account (others' jobs need AdminLevel=Operator
                       or above, or coordinator of it; without it the result
                       covers only your own jobs).
      -p, --partition  Report a partition.
      -d, --days       Window length in days (default 7).
      --since/--until  Explicit window, YYYY-mm-ddTHH:MM:SS.
    """
    if sum(bool(x) for x in (user, account, partition)) > 1:
        raise click.ClickException("give only one of -u / -A / -p")
    start, end = _window(days, since, until)
    scope_user = None if (account or partition) else (user or os.environ.get("USER", ""))
    rows = slurm.sacct_window_rows(
        _FIELDS, start, end, user=scope_user, account=account, partition=partition
    )

    samples: list[dict] = []
    pending = skew = malformed = 0
    for row in rows:
        if len(row) < 7 or not row[0].strip().isdigit():
            malformed += 1
            continue
        _, part, qos, submit, started, _state, tres = row[:7]
        if started in ("", "Unknown", "None", "NONE"):
            pending += 1
            continue
        try:
            wait_s = _epoch(started) - _epoch(submit)
        except ValueError:
            pending += 1
            continue
        if wait_s < 0:
            skew += 1
            continue
        samples.append(
            {
                "wait": wait_s,
                "partition": part,
                "qos": qos,
                "bucket": _bucket(slurm.parse_gpu_count(tres)),
            }
        )

    click.echo(f"Submit-to-start wait times  ({start} to {end})")
    click.echo()
    click.echo(
        f"  {len(samples)} started job(s); excluded {pending} pending, {skew} clock-skew; "
        f"{malformed} malformed row(s)"
    )
    click.echo("  (sacct cannot separate priority wait from resource wait)")

    def show(title: str, key: str) -> None:
        groups: dict[str, list[int]] = {}
        for item in samples:
            groups.setdefault(item[key], []).append(item["wait"])
        if not groups:
            return
        click.echo()
        click.echo(f"by {title}:")
        click.echo(f"  {'GROUP':<24}{'N':>6}{'P50':>10}{'P90':>10}{'MAX':>10}")
        for name in sorted(groups):
            values = sorted(groups[name])
            click.echo(
                f"  {name:<24}{len(values):>6}"
                f"{_humanize(slurm.percentile(values, 50)):>10}"
                f"{_humanize(slurm.percentile(values, 90)):>10}"
                f"{_humanize(values[-1]):>10}"
            )

    show("partition", "partition")
    show("QoS", "qos")
    show("GPU count", "bucket")
