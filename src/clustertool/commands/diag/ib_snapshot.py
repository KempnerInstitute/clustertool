"""diag ib-snapshot command."""

import json
import pathlib

import click

from clustertool import fabric
from clustertool.grouping import keywords


@keywords("infiniband", "capture", "forensic", "topology", "counters")
@click.command("ib-snapshot")
@click.argument("output", required=False, type=click.Path(dir_okay=False))
def ib_snapshot(output: str | None) -> None:
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
    """
    payload = json.dumps(fabric.collect_snapshot(), indent=2, default=str)
    if output:
        pathlib.Path(output).write_text(payload)
        click.echo(f"wrote {output}")
    else:
        click.echo(payload)
