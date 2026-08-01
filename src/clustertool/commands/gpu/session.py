"""gpu session command."""

import os
import socket

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords


def _jupyter_command(port: int) -> list[str]:
    """Return an srun command that launches Jupyter Lab on the allocated node.

    srun is required: salloc runs a command it is given on the submitting host,
    so a bare command would start the notebook on the login node while the GPU
    sat idle. Binding to the node's own hostname keeps it off other interfaces.
    """
    user = os.environ.get("USER", "")
    login_host = socket.gethostname()
    tunnel = f"ssh -N -L {port}:$(hostname):{port} {user}@{login_host}"
    inner = (
        f'echo "From your laptop, run: {tunnel}"; '
        f'echo "then open the http://127.0.0.1:{port}/ URL printed below"; '
        f'exec jupyter lab --no-browser --ip="$(hostname)" --port={port}'
    )
    return ["srun", "--pty", "bash", "-c", inner]


@keywords("shell", "salloc", "srun", "notebook", "jupyter", "devshell")
@click.command("session", context_settings={"ignore_unknown_options": True})
@click.argument("gpu_type", type=click.Choice(list(slurm.GPU_TYPE_PARTITION), case_sensitive=False))
@click.argument("salloc_args", nargs=-1, type=click.UNPROCESSED, metavar="[SALLOC_ARG]...")
@click.option(
    "-A",
    "--account",
    required=True,
    help="Fairshare account to charge.",
    shell_complete=completion.complete_accounts,
)
@click.option(
    "-t", "--time", "time_limit", default="0-01:00", show_default=True, help="Time limit (D-HH:MM)."
)
@click.option(
    "--jupyter", is_flag=True, help="Launch Jupyter Lab on the node and print the tunnel."
)
@click.option("--port", type=int, default=8888, show_default=True, help="Port for --jupyter.")
def session(
    gpu_type: str,
    salloc_args: tuple[str, ...],
    account: str,
    time_limit: str,
    jupyter: bool,
    port: int,
) -> None:
    """Start an interactive single-GPU session on a base partition (via salloc).

    GPU_TYPE selects the base partition, and the session requests one GPU plus
    the CPU and memory that partition enforces per GPU. Drops you into a shell
    on the node; exit it (or let the time limit lapse) to release the
    allocation. With --jupyter it runs Jupyter Lab on the allocated node through
    srun instead, bound to that node, and prints the SSH tunnel to reach it from
    your laptop.

    Extra arguments are forwarded to salloc after these defaults, so you can
    override or add any salloc flag (salloc uses the last value), for example
    'gpu session a100 -A LAB --mem=500000' or '... -J devshell'.

    The GPU types listed above are the ones your site defines under [gpu_types],
    each mapped to a partition whose per-GPU CPU and memory come from
    [partitions.limits]. Run 'nodes partitions' to see that mapping.

    \b
    Use cases:
      - Grab one GPU for interactive development or debugging.
      - Run a Jupyter notebook on a GPU node with --jupyter.

    \b
    Inputs:
      GPU_TYPE         One of a100, h100, h200, rtx.
      -A, --account    Fairshare account to charge (required).
      -t, --time       Time limit D-HH:MM (default 0-01:00).
      --jupyter        Launch Jupyter Lab on the node and print the SSH tunnel.
      --port           Port for --jupyter (default 8888).
      [SALLOC_ARG]...  Extra salloc arguments, forwarded (override the defaults).
    """
    partition = slurm.GPU_TYPE_PARTITION[gpu_type.lower()]
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
    if jupyter:
        cmd += _jupyter_command(port)
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
