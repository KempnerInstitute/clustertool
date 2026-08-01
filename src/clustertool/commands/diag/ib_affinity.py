"""diag ib-affinity command."""

import json
import pathlib

import click

from clustertool import fabric, process
from clustertool.grouping import keywords


@keywords("infiniband", "nic", "numa", "affinity", "pcie")
@click.command("ib-affinity")
@click.option(
    "--snapshot",
    "snapshot",
    type=click.Path(dir_okay=False),
    default=None,
    help="Read topology from an ib-snapshot JSON instead of probing.",
)
@click.pass_context
def ib_affinity(ctx: click.Context, snapshot: str | None) -> None:
    """Check GPU-to-IB-NIC NUMA affinity (via nvidia-smi topo -m).

    Each GPU's best link to an InfiniBand NIC should be NODE-level or closer; a
    SYS link (across the CPU interconnect) costs 30-50% of cross-node bandwidth.
    Run it on a GPU node. The exit code is 0 all NODE or better, 1 a GPU crosses
    NUMA, 2 a GPU reaches no NIC, 3 probe or parse error.

    \b
    Use cases:
      - Confirm every GPU has a same-NUMA path to an IB NIC before a run.
      - Triage a node that gets poor cross-node bandwidth.

    \b
    Inputs:
      --snapshot  Analyze a saved ib-snapshot JSON instead of probing the node.
    """
    if snapshot:
        try:
            raw = json.loads(pathlib.Path(snapshot).read_text())["topology"]["raw"]
        except OSError as exc:
            click.echo(f"ib-affinity: error: cannot read {snapshot}: {exc}", err=True)
            ctx.exit(3)
        except (ValueError, KeyError, TypeError):
            click.echo(
                f"ib-affinity: error: {snapshot} is not an ib-snapshot file (no topology.raw)",
                err=True,
            )
            ctx.exit(3)
    else:
        code, raw, err = process.probe(["nvidia-smi", "topo", "-m"], timeout=30)
        if code == 127:
            click.echo("ib-affinity: error: nvidia-smi not found on this host", err=True)
            ctx.exit(3)
        if code == 124:
            click.echo("ib-affinity: error: nvidia-smi timed out after 30s", err=True)
            ctx.exit(3)
        if code:
            click.echo(f"ib-affinity: error: nvidia-smi failed: {err.strip() or code}", err=True)
            ctx.exit(3)

    if not raw.strip():
        click.echo("ib-affinity: error: no topology data available", err=True)
        ctx.exit(3)
    matrix = fabric.parse_topo(raw)
    if not matrix:
        click.echo(
            "ib-affinity: error: the topology matrix lists no GPU-to-NIC pairs; "
            "this node exposes no RDMA NICs to nvidia-smi",
            err=True,
        )
        ctx.exit(3)

    rows = fabric.affinity_rows(matrix)
    nic_count = len(next(iter(matrix.values())))
    click.echo(f"{len(matrix)} GPU(s) x {nic_count} NIC(s)")
    click.echo(f"{'GPU':<6} {'BEST NIC':<9} {'QUALITY':<8} VERDICT")
    fails = warns = 0
    for gpu, best_nic, best_q, verdict in rows:
        detail = verdict if verdict != "WARN" else f"WARN (across {best_q})"
        click.echo(f"{gpu:<6} {best_nic:<9} {best_q:<8} {detail}")
        if verdict == "FAIL":
            fails += 1
        elif verdict == "WARN":
            warns += 1

    if fails:
        click.echo(f"\nFAIL: {fails} GPU(s) reach no NIC")
        ctx.exit(2)
    if warns:
        click.echo(
            f"\nWARN: {warns} GPU(s) cross a NUMA boundary (expect 30-50% cross-node BW loss)"
        )
        ctx.exit(1)
    click.echo("\nOK: every GPU is NODE-level or closer to an IB NIC")
    ctx.exit(0)
