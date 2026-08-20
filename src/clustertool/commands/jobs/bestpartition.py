"""jobs best-partition command."""

import datetime
import os
import pathlib
import pwd
import re
import sys

import click

from clustertool import completion, slurm, storage
from clustertool.grouping import keywords

_SCRIPT_ACCOUNT_RE = re.compile(r"^#SBATCH\s+(?:-A|--account)[=\s]+(\S+)", re.M)
_TIME_FMT = "%Y-%m-%dT%H:%M:%S"
_BAD_ARGUMENT = "unrecognized option"
"""How sbatch reports a flag it does not know, which every partition would repeat."""

_STAND_IN_TIME = "1:00:00"
"""Time limit given to a stand-in job when the caller names none.

A site may require one, and an estimate needs a duration to mean anything.
"""


def _asks_for_time(args: list[str]) -> bool:
    """Return True if the caller set a time limit, in any of sbatch's flag forms.

    --time-min is a floor rather than a limit, so it does not count.
    """
    return any(arg.startswith("-t") or arg == "--time" or arg.startswith("--time=") for arg in args)


def _script_index(args: list[str]) -> int:
    """Return where a script sits among sbatch arguments, or -1 if none does.

    sbatch takes the script positionally, so it is accepted that way here too. A
    path a flag is consuming, such as the one after -o, is not the script. The
    caller lifts it out of the arguments, because sbatch stops reading flags at
    the script and would pass the rest to it.
    """
    for index in range(len(args) - 1, -1, -1):
        arg = args[index]
        if arg.startswith("-") or not pathlib.Path(arg).is_file():
            continue
        if index and args[index - 1].startswith("-"):
            continue
        return index
    return -1


def _script_account(path: str) -> str:
    """Return the account a submission script asks for, or "" if it names none."""
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    match = _SCRIPT_ACCOUNT_RE.search(text)
    return match.group(1) if match else ""


def _delay(estimate: str, now: datetime.datetime) -> int:
    """Return seconds from now until an estimated start, never negative.

    Slurm answers with a timestamp, and one just past means the job starts now.
    """
    try:
        start = datetime.datetime.strptime(estimate, _TIME_FMT)
    except ValueError:
        return 0
    return max(int((start - now).total_seconds()), 0)


def _candidates(account: str, user: str) -> tuple[list[str], dict[str, int]]:
    """Return the partitions worth asking about, and a count per reason for the rest."""
    groups = set(storage.user_groups(user))
    open_to_me: list[str] = []
    refused: dict[str, int] = {}
    for record in slurm.partition_records():
        refusal = slurm.partition_refusal(record, groups, account)
        if refusal:
            refused[refusal] = refused.get(refusal, 0) + 1
        else:
            open_to_me.append(record["PartitionName"])
    return sorted(open_to_me), refused


def _caller() -> str:
    """Return the current username, from the environment or the uid behind it."""
    named = os.environ.get("USER")
    if named:
        return named
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return ""


def _progress(text: str) -> None:
    """Overwrite a single status line, only where a terminal can redraw it."""
    if sys.stderr.isatty() and os.environ.get("TERM", "") not in ("", "dumb"):
        click.echo(f"\r\033[K{text}", nl=False, err=True)


@keywords("where", "soonest", "fastest", "eta", "delay", "start", "queue", "shop")
@click.command("best-partition", context_settings={"ignore_unknown_options": True})
@click.option(
    "-f",
    "--file",
    "script",
    type=click.Path(exists=True, dir_okay=False),
    help="Submission script to test.",
)
@click.option(
    "-p",
    "--partition",
    "wanted",
    multiple=True,
    shell_complete=completion.complete_partitions,
    help="Test only these partitions.",
)
@click.option(
    "-A",
    "--account",
    shell_complete=completion.complete_accounts,
    help="Account to test under (default: the script's, else yours).",
)
@click.option(
    "-l",
    "--limit",
    type=click.IntRange(min=1),
    default=40,
    show_default=True,
    help="Most partitions to ask about.",
)
@click.option(
    "--timeout",
    type=click.FloatRange(min=1),
    default=10.0,
    show_default=True,
    help="Seconds to wait per partition.",
)
@click.argument("sbatch_args", nargs=-1, type=click.UNPROCESSED, metavar="[SCRIPT] [SBATCH_ARG]...")
def best_partition(
    script: str | None,
    wanted: tuple[str, ...],
    account: str | None,
    limit: int,
    timeout: float,
    sbatch_args: tuple[str, ...],
) -> None:
    """Find the partition where your job would start soonest.

    Asks the controller, once per partition, when it would schedule this job, and
    sorts the answers. The estimate is Slurm's own, from sbatch --test-only, and
    nothing is submitted. A partition that cannot run the job at all reports why,
    which is usually the more useful answer: a missing GPU request or a time limit
    the partition does not accept.

    Partitions your groups and account cannot use are dropped first, from what
    scontrol publishes. A rule a site applies at submission is not visible there,
    so it appears as a refusal instead.

    \b
    Use cases:
      - Decide where to submit a script you already have.
      - Price a request before writing a script at all, with sbatch flags.
      - Find out why a partition refuses a job without submitting it.

    \b
    Inputs:
      SCRIPT            Submission script to test, named the way sbatch takes
                        it, or with -f. Without one, a trivial job stands in, so
                        flags alone can be compared.
      -f, --file        The script, for callers who prefer a flag.
      -p, --partition   Test only these partitions, repeatable. Skips the
                        eligibility scan and asks about exactly these.
      -A, --account     Account to test under (default: the script's, else your
                        default account).
      -l, --limit       Most partitions to ask about (default 40).
      --timeout         Seconds to wait per partition (default 10).
      [SBATCH_ARG]...   Extra sbatch flags, such as -t 2:00:00 --gpus 1
                        --mem 32G, applied to every partition tested. They may
                        surround the script, as they would for sbatch.

    Partitions are asked one at a time, so a wide search costs a second or two
    per partition. Naming partitions with -p keeps it short.
    """
    user = _caller()
    extra = list(sbatch_args)
    if not script:
        at = _script_index(extra)
        if at >= 0:
            script = extra.pop(at)
    chosen_account = (
        account
        or (_script_account(script) if script else "")
        or (slurm.default_account(user) if user else "")
    )
    if account:
        extra += ["-A", account]
    if not script and not _asks_for_time(extra):
        extra += ["-t", _STAND_IN_TIME]

    dropped = 0
    if wanted:
        partitions, refused = list(wanted), {}
    else:
        partitions, refused = _candidates(chosen_account, user)
        dropped = max(len(partitions) - limit, 0)
        partitions = partitions[:limit]
    if not partitions:
        raise click.ClickException("no partition is open to you, so there is nothing to compare")

    what = script or " ".join(extra) or f"a stand-in job of {_STAND_IN_TIME}"
    click.echo(f"Earliest start for {what}, account {chosen_account or 'unknown'}")
    click.echo(f"  asking {len(partitions)} partition(s), one at a time; nothing is submitted")
    if refused:
        summary = ", ".join(f"{count} {reason}" for reason, count in sorted(refused.items()))
        click.echo(f"  skipped {sum(refused.values())}: {summary}")
    if dropped > 0:
        click.echo(f"  {dropped} more not asked about, over the --limit of {limit}")
    click.echo()

    now = datetime.datetime.now()
    starts: list[tuple[int, str, str]] = []
    refusals: list[tuple[str, str]] = []
    for index, partition in enumerate(partitions, start=1):
        _progress(f"  asking {partition} ({index}/{len(partitions)})")
        kind, detail = slurm.start_estimate(partition, extra, script or "", timeout)
        if kind == "start":
            starts.append((_delay(detail, now), partition, detail))
        else:
            if detail.startswith(_BAD_ARGUMENT):
                _progress("")
                raise click.ClickException(f"sbatch {detail}")
            refusals.append((partition, detail))
    _progress("")

    ranked = sorted(starts)
    if ranked:
        click.echo(f"  {'PARTITION':<28}{'STARTS IN':>12}   WHEN")
        for delay, partition, estimate in ranked:
            when = "now" if delay == 0 else slurm.humanize_seconds(delay)
            click.echo(f"  {partition:<28}{when:>12}   {estimate}")
    else:
        click.echo("  no partition would run this job as requested")

    if refusals:
        click.echo()
        reasons = {reason for _, reason in refusals}
        if len(reasons) == 1 and len(refusals) > 1:
            click.echo(f"All {len(refusals)} refused for the same reason: {reasons.pop()}")
        else:
            click.echo("Cannot run it:")
            width = max(len(partition) for partition, _ in refusals)
            for partition, reason in refusals:
                click.echo(f"  {partition:<{width}}  {reason}")

    if starts:
        command = " ".join(["sbatch", "-p", ranked[0][1], *extra, script or "<script>"])
        click.echo()
        click.echo(f"Submit there with: {command}")
