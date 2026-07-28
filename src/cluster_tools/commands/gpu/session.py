"""gpu session command."""

import click

from cluster_tools import process, slurm
from cluster_tools.grouping import keywords

_GPU_PARTITION = {
    "a100": "kempner",
    "h100": "kempner_h100",
    "h200": "kempner_h200",
    "rtx": "kempner_rtx",
}


@keywords("shell", "salloc", "srun", "notebook", "devshell")
@click.command("session", context_settings={"ignore_unknown_options": True})
@click.argument("gpu_type", type=click.Choice(list(_GPU_PARTITION), case_sensitive=False))
@click.argument("salloc_args", nargs=-1, type=click.UNPROCESSED, metavar="[SALLOC_ARG]...")
@click.option("-A", "--account", required=True, help="Fairshare account to charge.")
@click.option(
    "-t", "--time", "time_limit", default="0-01:00", show_default=True, help="Time limit (D-HH:MM)."
)
def session(gpu_type: str, salloc_args: tuple[str, ...], account: str, time_limit: str) -> None:
    """Start an interactive single-GPU session on a Kempner partition (via salloc).

    GPU_TYPE selects the base partition, and the session requests one GPU plus
    the CPU and memory that partition enforces per GPU. Drops you into a shell
    on the node; exit it (or let the time limit lapse) to release the
    allocation.

    Extra arguments are forwarded to salloc after these defaults, so you can
    override or add any salloc flag (salloc uses the last value), for example
    'gpu session a100 -A LAB --mem=500000' or '... -J devshell'.

    \b
    Per-GPU resources (one GPU each):
      a100  kempner        16 CPU, 240000 MB
      h100  kempner_h100   24 CPU, 360000 MB
      h200  kempner_h200   16 CPU, 360000 MB
      rtx   kempner_rtx    16 CPU, 180000 MB

    \b
    Use cases:
      - Grab one GPU for interactive development or debugging.

    \b
    Inputs:
      GPU_TYPE         One of a100, h100, h200, rtx.
      -A, --account    Fairshare account to charge (required).
      -t, --time       Time limit D-HH:MM (default 0-01:00).
      [SALLOC_ARG]...  Extra salloc arguments, forwarded (override the defaults).
    """
    partition = _GPU_PARTITION[gpu_type.lower()]
    cpus, mem_mb = slurm.PARTITION_LIMITS[partition]
    cmd = [
        "salloc",
        "-p",
        partition,
        "--account=" + account,
        "--gres=gpu:1",
        "--cpus-per-task=" + str(cpus),
        "--mem=" + str(mem_mb),
        "-t",
        time_limit,
        *salloc_args,
    ]
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
