"""diag io-probe command."""

import click

from cluster_tools import ioprobe
from cluster_tools.grouping import keywords


@keywords("filesystem", "throughput", "latency", "storage", "responsiveness")
@click.command("io-probe")
@click.option(
    "-d",
    "--dir",
    "directory",
    required=True,
    metavar="TARGET",
    help="Directory to probe (a scratch subdir is created inside).",
)
@click.option(
    "--size",
    type=float,
    default=256.0,
    show_default=True,
    metavar="MB",
    help="Sequential file size in MB.",
)
@click.option(
    "--meta-files",
    "meta_files",
    type=int,
    default=100,
    show_default=True,
    help="Metadata batch size.",
)
@click.option(
    "--min-write",
    "min_write",
    type=float,
    default=None,
    metavar="MBS",
    help="Fail if write MB/s is below this.",
)
@click.option(
    "--min-read",
    "min_read",
    type=float,
    default=None,
    metavar="MBS",
    help="Fail if read MB/s is below this.",
)
@click.option(
    "--max-meta-ms",
    "max_meta_ms",
    type=float,
    default=None,
    metavar="MS",
    help="Fail if metadata ms/op exceeds this.",
)
@click.option("--keep", is_flag=True, help="Keep the scratch subdir.")
@click.option("--json", "as_json", is_flag=True, help="Emit the structured result as JSON.")
@click.pass_context
def io_probe(
    ctx: click.Context,
    directory: str,
    size: float,
    meta_files: int,
    min_write: float | None,
    min_read: float | None,
    max_meta_ms: float | None,
    keep: bool,
    as_json: bool,
) -> None:
    """Probe a filesystem's write/read throughput and metadata latency.

    Writes a bounded file (fsync included), re-reads it (page-cache assisted),
    and times create/stat/delete on a batch of small files, against a scratch
    subdirectory of the target. Not a benchmark. Run it on a compute node (wrap
    in srun) to probe from there. Set --min-write, --min-read, or --max-meta-ms
    to turn it into a pass/fail gate. The exit code is 0 report or pass, 2 a gate
    missed, 3 setup or IO error.

    \b
    Use cases:
      - Spot-check whether a filesystem is responsive from a node.
      - Gate a job on minimum IO throughput in a health check.

    \b
    Inputs:
      -d, --dir     Directory to probe.
      --size        Sequential file size in MB (default 256).
      --meta-files  Metadata batch size (default 100).
      --min-write, --min-read, --max-meta-ms  Gate thresholds.
      --keep        Keep the scratch subdir.
      --json        Emit JSON instead of the text report.
    """
    if size <= 0 or meta_files <= 0:
        click.echo("io-probe: error: --size and --meta-files must be > 0", err=True)
        ctx.exit(3)
    try:
        metrics = ioprobe.run_probe(directory, size, meta_files, keep=keep)
    except ioprobe.ProbeError as exc:
        click.echo(f"io-probe: error: {exc}", err=True)
        ctx.exit(3)
    gates = {"min_write": min_write, "min_read": min_read, "max_meta_ms": max_meta_ms}
    status, reasons = ioprobe.verdict(metrics, gates)
    if as_json:
        click.echo(ioprobe.render_json(metrics, gates, status, reasons))
    else:
        click.echo(ioprobe.render(metrics, status, reasons))
    ctx.exit(2 if status == "FAIL" else 0)
