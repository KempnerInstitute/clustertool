"""diag ib command."""

import concurrent.futures

import click

from clustertool import completion, process, qos, slurm
from clustertool.grouping import admin, keywords

_SSH_OPTS = [
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "LogLevel=ERROR",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=5",
]
_SENTINEL = "__clustertool_ports__"
_SSH_TIMEOUT_S = 30

_IB_CHECK = f"""
ports=0
for s in /sys/class/infiniband/*/ports/*/state; do
  [ -e "$s" ] || continue
  p=${{s%/state}}
  case "$(cat "$p/link_layer" 2>/dev/null)" in InfiniBand) ;; *) continue ;; esac
  ports=$((ports+1))
  state=$(cat "$s" 2>/dev/null)
  case "$state" in *ACTIVE*) ;; *) echo "${{p#/sys/class/infiniband/}} $state" ;; esac
done
echo "{_SENTINEL} $ports"
"""


def _host_ib_state(host: str) -> tuple[str, str]:
    """Return (status, detail) for a host's InfiniBand ports.

    Status is 'ok', 'down', 'no-ib', or 'unreachable'. The remote script always
    prints a sentinel, so a host that never answered is told apart from one whose
    ports are all up, rather than both looking like a clean result.
    """
    code, out, err = process.probe(["ssh", *_SSH_OPTS, host, _IB_CHECK], timeout=_SSH_TIMEOUT_S)
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    marker = [line for line in lines if line.startswith(_SENTINEL)]
    if code != 0 or not marker:
        return "unreachable", (err.strip().splitlines() or ["ssh failed"])[0]
    count = marker[0].split()[-1]
    down = [line for line in lines if not line.startswith(_SENTINEL)]
    if count == "0":
        return "no-ib", "no InfiniBand ports"
    if down:
        return "down", "\n".join(down)
    return "ok", ""


@admin
@keywords("infiniband", "network", "fabric")
@click.command("ib")
@click.argument(
    "partitions",
    nargs=-1,
    required=True,
    metavar="PARTITION...",
    shell_complete=completion.complete_partitions,
)
@click.option(
    "--parallel",
    type=click.IntRange(min=1),
    default=24,
    show_default=True,
    help="Maximum parallel ssh checks.",
)
@click.pass_context
def ib(ctx: click.Context, partitions: tuple[str, ...], parallel: int) -> None:
    """Report nodes whose InfiniBand ports are not ACTIVE, in one or more partitions.

    For each partition, ssh to its nodes in parallel and read each InfiniBand
    port's state from /sys/class/infiniband, which is what the RDMA stack itself
    reports. A port whose link layer is Ethernet is not InfiniBand and is not
    counted.

    A host that could not be reached is reported as unreachable rather than
    counted as healthy, so a run that contacted nothing cannot read as a clean
    fabric.

    Needs ssh to every node in the partition, not only the ones running your jobs.
    Where node login requires an allocation on that node, as pam_slurm_adopt
    enforces, an ordinary user sees every host unreachable.

    \b
    Exit codes:
      0  every reachable host has all InfiniBand ports ACTIVE
      1  some hosts were unreachable, or have no InfiniBand ports
      2  at least one host has an InfiniBand port that is not ACTIVE
      3  a partition does not exist

    \b
    Use cases:
      - Find nodes with a downed IB link before scheduling a large job.
      - Spot-check fabric health across a partition.

    \b
    Inputs:
      PARTITION...  One or more Slurm partition names.
      --parallel    Maximum parallel ssh checks (default 24).
    """
    worst = 0
    for partition in partitions:
        nodes = [name for name, _ in slurm.partition_nodes(partition)]
        if not nodes:
            if not qos.partition_exists(partition):
                click.echo(f"diag ib: error: partition '{partition}' does not exist", err=True)
                ctx.exit(3)
            click.echo(f"== {partition} (0 node(s)) ==")
            click.echo("  (no nodes)")
            click.echo()
            continue

        click.echo(f"== {partition} ({len(nodes)} node(s)) ==")
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as pool:
            for host, result in zip(nodes, pool.map(_host_ib_state, nodes), strict=True):
                results[host] = result

        down = {h: d for h, (s, d) in results.items() if s == "down"}
        unreachable = sorted(h for h, (s, _) in results.items() if s == "unreachable")
        no_ib = sorted(h for h, (s, _) in results.items() if s == "no-ib")
        ok = sum(1 for s, _ in results.values() if s == "ok")

        for host in sorted(down):
            click.echo(f"  {host}:")
            for line in down[host].splitlines():
                click.echo(f"    {line}")
        click.echo(
            f"  >>> {len(down)} down, {ok} ok, {len(no_ib)} without IB, "
            f"{len(unreachable)} unreachable"
        )
        for label, hosts in (("unreachable", unreachable), ("without IB", no_ib)):
            if hosts:
                shown = ", ".join(hosts[:8])
                more = f", and {len(hosts) - 8} more" if len(hosts) > 8 else ""
                click.echo(f"  {label}: {shown}{more}")
        click.echo()

        if down:
            worst = max(worst, 2)
        elif unreachable or no_ib:
            worst = max(worst, 1)
    ctx.exit(worst)
