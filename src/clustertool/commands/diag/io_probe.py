"""diag io-probe command."""

import click

from clustertool import ioprobe
from clustertool.grouping import keywords


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
    type=click.FloatRange(min=4.0),
    default=256.0,
    show_default=True,
    metavar="MIB",
    help="Sequential file size in MiB, rounded down to a whole 4 MiB chunk.",
)
@click.option(
    "--min-write",
    "min_write",
    type=float,
    default=None,
    metavar="MIBS",
    help="Fail if write MiB/s is below this.",
)
@click.option(
    "--min-read",
    "min_read",
    type=float,
    default=None,
    metavar="MIBS",
    help="Fail if read MiB/s is below this.",
)
@click.option(
    "--max-meta-ms",
    "max_meta_ms",
    type=float,
    default=None,
    metavar="MS",
    help="Fail if metadata ms/op exceeds this.",
)
@click.option(
    "--meta-files",
    "meta_files",
    type=click.IntRange(min=1),
    default=100,
    show_default=True,
    help="Metadata batch size.",
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

    Writes a bounded file of random data (fsync included), re-reads it after
    dropping its page cache, and times create/stat/delete on a batch of small
    files, against a scratch subdirectory of the target. Not a benchmark. Run it
    on a compute node (wrap in srun) to probe from there; on a login node it
    measures that node's client and whatever else is contending on it.

    Every figure is MiB and MiB/s. The file is written in whole 4 MiB chunks, so
    --size rounds down to a multiple of that, and each chunk is fresh random
    data, since a compressing or deduplicating backend does not store a repeated
    one. tmpfs and ramfs are refused: they are memory rather than storage, and
    posix_fadvise reports dropping their cache while evicting nothing, so a probe
    there would report the memory subsystem as a filesystem.

    Set --min-write, --min-read, or --max-meta-ms to turn it into a pass/fail
    gate. The exit code is 0 report or pass, 3 setup or IO error, 4 a gate missed.
    2 is unused throughout the diagnostics, since click exits 2 on a usage error.

    \b
    Use cases:
      - Spot-check whether a filesystem is responsive from a node.
      - Gate a job on minimum IO throughput in a health check.

    \b
    Inputs:
      -d, --dir     Directory to probe.
      --size        Sequential file size in MiB (default 256), rounded down to a
                    whole 4 MiB chunk.
      --meta-files  Metadata batch size (default 100).
      --min-write, --min-read, --max-meta-ms  Gate thresholds.
      --keep        Keep the scratch subdir.
      --json        Emit JSON instead of the text report.
    """
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
    ctx.exit(4 if status == "FAIL" else 0)
