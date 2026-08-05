"""diag ib-snapshot command."""

import json
import pathlib

import click

from clustertool import fabric
from clustertool.grouping import keywords


@keywords("infiniband", "capture", "forensic", "topology", "counters")
@click.command("ib-snapshot")
@click.argument("output", required=False, type=click.Path(dir_okay=False))
@click.pass_context
def ib_snapshot(ctx: click.Context, output: str | None) -> None:
    """Capture a node's IB and GPU topology and counters as a JSON snapshot.

    Probes GPUs, the NVLink status, the GPU-to-NIC topology matrix, and each
    InfiniBand HCA's port state, rate, and error counters, into one JSON file for
    forensic comparison and for diffing across a run. Read-only. Run it on the
    node. Write to OUTPUT, or print to stdout to redirect. Feed two snapshots to
    diag ib-counters, or one to diag ib-affinity --snapshot.

    Any probe that could not run is recorded under probe_errors, so an empty field
    means the node genuinely had nothing to report rather than that the tool was
    missing or timed out.

    \b
    Use cases:
      - Capture a node's fabric state when it goes slow, for later comparison.
      - Bracket a benchmark with two snapshots to check for counter growth.

    \b
    Inputs:
      OUTPUT  File to write the JSON snapshot to (default: stdout).

    \b
    Exit codes:
      0  the snapshot was taken, though probe_errors may not be empty
      3  the node could not be probed, or the file could not be written
    2 is unused throughout the diagnostics, since click exits 2 on a usage error.
    """
    try:
        snapshot = fabric.collect_snapshot()
    except (OSError, ValueError) as exc:
        click.echo(f"ib-snapshot: error: could not probe this node: {exc}", err=True)
        ctx.exit(3)
    payload = json.dumps(snapshot, indent=2, default=str)
    for probe, reason in sorted(snapshot.get("probe_errors", {}).items()):
        click.echo(f"ib-snapshot: warning: {probe}: {reason}", err=True)
    if not output:
        click.echo(payload)
        return
    try:
        pathlib.Path(output).write_text(payload)
    except OSError as exc:
        click.echo(f"ib-snapshot: error: cannot write {output}: {exc}", err=True)
        click.echo(payload)
        ctx.exit(3)
    click.echo(f"wrote {output}")
