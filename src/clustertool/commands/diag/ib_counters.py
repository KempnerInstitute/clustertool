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
    means the fabric hiccupped. The exit code is 0 no error growth, 3 a file
    could not be read, 4 an error-class counter advanced. 2 is unused throughout
    the diagnostics, since click exits 2 on a usage error.

    \b
    Use cases:
      - Confirm a benchmark did not degrade the fabric.
      - Localize which port grew errors during a run.

    \b
    Inputs:
      BEFORE  The earlier ib-snapshot JSON.
      AFTER   The later ib-snapshot JSON.
    """
    snapshots = []
    for label, path in (("BEFORE", before), ("AFTER", after)):
        try:
            snapshots.append(json.loads(pathlib.Path(path).read_text()))
        except OSError as exc:
            click.echo(f"ib-counters: error: cannot read {label} {path}: {exc}", err=True)
            ctx.exit(3)
        except ValueError as exc:
            click.echo(f"ib-counters: error: {label} {path} is not valid JSON: {exc}", err=True)
            ctx.exit(3)
    before_snap, after_snap = snapshots
    for label, path, snap in (("BEFORE", before, before_snap), ("AFTER", after, after_snap)):
        try:
            fabric.require_snapshot(snap, f"{label} {path}")
        except ValueError as exc:
            click.echo(f"ib-counters: error: {exc}", err=True)
            ctx.exit(3)
    named = [("BEFORE", before_snap.get("hostname")), ("AFTER", after_snap.get("hostname"))]
    missing = [label for label, host in named if not host]
    if missing:
        click.echo(
            f"ib-counters: error: {' and '.join(missing)} records no hostname, so this "
            "cannot tell whether the two snapshots are from the same node. HCA names "
            "repeat across nodes, and diffing two of them compares unrelated ports",
            err=True,
        )
        ctx.exit(3)
    hosts = {host.split(".")[0] for _, host in named}
    if len(hosts) > 1:
        listed = ", ".join(sorted(host for _, host in named))
        click.echo(
            f"ib-counters: error: the snapshots are from different hosts ({listed}); "
            "HCA names repeat across nodes, so diffing them compares unrelated ports",
            err=True,
        )
        ctx.exit(3)

    if not (fabric.counters_by_port(before_snap) or fabric.counters_by_port(after_snap)):
        click.echo(
            "ib-counters: error: neither snapshot has an InfiniBand port to compare, "
            "so this run measured nothing",
            err=True,
        )
        ctx.exit(3)
    rows, any_error = fabric.counter_deltas(before_snap, after_snap)
    saturated = False
    click.echo(f"{'PORT':<20} {'COUNTER':<40} {'BEFORE':>12} {'AFTER':>12} {'DELTA':>12}")
    for port, counter, before_v, after_v, delta, is_error in rows:
        if delta is None:
            tag = " UNREADABLE" if is_error else " unreadable"
            shown = "?"
        elif delta < 0:
            tag = " RESET" if is_error else " reset"
            shown = f"{delta:+}"
        elif is_error and delta == 0 and after_v in fabric.SATURATED_COUNTER_VALUES:
            tag = " SATURATED"
            shown = "+0"
            saturated = True
        else:
            tag = " ERROR" if is_error else ""
            shown = f"{delta:+}"
        click.echo(
            f"{port:<20} {counter:<40} {_num(before_v):>12} {_num(after_v):>12} {shown:>12}{tag}"
        )

    if saturated:
        click.echo(
            "\nFAIL: an error-class counter is pegged at its maximum. IBTA counters "
            "stop at the top rather than wrapping, so it records no further errors "
            "and a delta of zero from it means nothing"
        )
        ctx.exit(4)
    if any_error:
        click.echo("\nFAIL: an error-class counter advanced, reset, or could not be read")
        ctx.exit(4)
    click.echo("\nOK: no error-class counter growth")
    ctx.exit(0)
