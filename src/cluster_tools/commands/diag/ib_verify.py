"""diag ib-verify command."""

import json
import pathlib

import click

from cluster_tools import fabric
from cluster_tools.grouping import keywords


@keywords("infiniband", "topology", "golden", "drift", "verify")
@click.command("ib-verify")
@click.argument("golden", type=click.Path(dir_okay=False))
@click.option(
    "--current",
    "current_file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Use an existing snapshot instead of probing this node.",
)
@click.option("--save-golden", is_flag=True, help="Save the current snapshot as GOLDEN and exit.")
@click.option("--strict", is_flag=True, help="Count driver/kernel/CUDA drift as drift too.")
@click.option("--json", "as_json", is_flag=True, help="Emit the findings as JSON.")
@click.pass_context
def ib_verify(
    ctx: click.Context,
    golden: str,
    current_file: str | None,
    save_golden: bool,
    strict: bool,
    as_json: bool,
) -> None:
    """Compare a node's IB/GPU snapshot against a golden one and report drift.

    Diffs the current snapshot (a fresh probe, or --current FILE) against the
    GOLDEN snapshot. Identity fields are compared (GPU inventory, HCA port state
    and rate, netdev mapping, topology); volatile fields (counters, temps) are
    ignored. Driver, kernel, and CUDA changes are informational and count as
    drift only with --strict. Bless a baseline with --save-golden. The exit code
    is 0 match, 1 drift, 3 setup error.

    \b
    Use cases:
      - Detect a swapped or downgraded HCA, or a changed link rate, on a node.
      - Bless a known-good node with --save-golden, then check it over time.

    \b
    Inputs:
      GOLDEN          The golden snapshot file to compare against (or write).
      --current       Compare an existing snapshot instead of probing.
      --save-golden   Save the current snapshot as GOLDEN and exit.
      --strict        Count driver/kernel/CUDA drift as drift.
      --json          Emit the findings as JSON.
    """
    try:
        if current_file:
            current = json.loads(pathlib.Path(current_file).read_text())
        else:
            current = fabric.collect_snapshot()
    except (OSError, ValueError) as exc:
        click.echo(f"ib-verify: error: cannot obtain current snapshot: {exc}", err=True)
        ctx.exit(3)

    if save_golden:
        try:
            pathlib.Path(golden).write_text(json.dumps(current, indent=2, default=str))
        except OSError as exc:
            click.echo(f"ib-verify: error: cannot write golden: {exc}", err=True)
            ctx.exit(3)
        click.echo(f"golden saved: {golden}")
        return

    try:
        golden_snap = json.loads(pathlib.Path(golden).read_text())
    except (OSError, ValueError):
        click.echo(
            f"ib-verify: error: no golden snapshot at {golden}; create one with --save-golden",
            err=True,
        )
        ctx.exit(3)

    findings = fabric.compare_snapshots(golden_snap, current)
    if as_json:
        click.echo(json.dumps(findings, indent=2))
    else:
        click.echo(fabric.render_drift(findings, strict))
    drift = findings["hardware"] or (strict and findings["informational"])
    ctx.exit(1 if drift else 0)
