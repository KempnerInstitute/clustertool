"""diag ib-counters command."""

import json
import pathlib

import click

from cluster_tools import fabric
from cluster_tools.grouping import keywords


@keywords("infiniband", "counters", "errors", "delta", "diff")
@click.command("ib-counters")
@click.argument("before", type=click.Path(exists=True, dir_okay=False))
@click.argument("after", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def ib_counters(ctx: click.Context, before: str, after: str) -> None:
    """Diff two ib-snapshot files for InfiniBand error-counter growth.

    Compares the per-port counters in a BEFORE and AFTER snapshot (from diag
    ib-snapshot, bracketing a run). Benign traffic counters are ignored; growth
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
        tag = " ERROR" if is_error else ""
        click.echo(f"{port:<20} {counter:<40} {before_v:>12} {after_v:>12} {delta:>+12}{tag}")

    if any_error:
        click.echo("\nFAIL: error-class counters advanced during the window")
        ctx.exit(2)
    click.echo("\nOK: no error-class counter growth")
    ctx.exit(0)
