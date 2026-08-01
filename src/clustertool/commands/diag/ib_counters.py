"""diag ib-counters command."""

import json
import pathlib

import click

from clustertool import fabric
from clustertool.grouping import keywords


def _num(value) -> str:
    """Render a counter, or ? when the snapshot could not read it."""
    return "?" if value is None else str(value)


@keywords("infiniband", "counters", "errors", "delta", "diff")
@click.command("ib-counters")
@click.argument("before", type=click.Path(dir_okay=False))
@click.argument("after", type=click.Path(dir_okay=False))
@click.pass_context
def ib_counters(ctx: click.Context, before: str, after: str) -> None:
    """Diff two ib-snapshot files for InfiniBand error-counter growth.

    Compares the per-port counters in a BEFORE and AFTER snapshot (from diag
    ib-snapshot, bracketing a run). Benign traffic counters are shown but do not
    fail the check; growth
    on an error-class counter (symbol errors, discards, link recoveries, ...)
    means the fabric hiccupped. The exit code is 0 no error growth, 2 an
    error-class counter advanced, 3 a file could not be read.

    \b
    Use cases:
      - Confirm a benchmark did not degrade the fabric.
      - Localize which port grew errors during a run.

    \b
    Inputs:
      BEFORE  The earlier ib-snapshot JSON.
      AFTER   The later ib-snapshot JSON.
    """
    try:
        before_snap = json.loads(pathlib.Path(before).read_text())
        after_snap = json.loads(pathlib.Path(after).read_text())
    except (OSError, ValueError) as exc:
        click.echo(f"ib-counters: error: {exc}", err=True)
        ctx.exit(3)

    rows, any_error = fabric.counter_deltas(before_snap, after_snap)
    click.echo(f"{'PORT':<20} {'COUNTER':<40} {'BEFORE':>12} {'AFTER':>12} {'DELTA':>12}")
    for port, counter, before_v, after_v, delta, is_error in rows:
        if delta is None:
            tag = " UNREADABLE" if is_error else " unreadable"
            shown = "?"
        elif delta < 0:
            tag = " RESET" if is_error else " reset"
            shown = f"{delta:+}"
        else:
            tag = " ERROR" if is_error else ""
            shown = f"{delta:+}"
        click.echo(
            f"{port:<20} {counter:<40} {_num(before_v):>12} {_num(after_v):>12} {shown:>12}{tag}"
        )

    if any_error:
        click.echo("\nFAIL: an error-class counter advanced, reset, or could not be read")
        ctx.exit(2)
    click.echo("\nOK: no error-class counter growth")
    ctx.exit(0)
