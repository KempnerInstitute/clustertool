"""diag nccl command."""

import importlib.resources
import os
import pathlib
import socket

import click

from cluster_tools import process, slurm


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


@click.command("nccl")
@click.option(
    "--python",
    "python_bin",
    default="python",
    show_default=True,
    help="Python interpreter with torch to run the test.",
)
@click.option("--timeout", "timeout_s", default=300, show_default=True, help="Timeout in seconds.")
@click.option("--dry-run", is_flag=True, help="Print the srun command without running it.")
def nccl(python_bin: str, timeout_s: int, dry_run: bool) -> None:
    """Run a multi-node FSDP NCCL sanity check inside a Slurm allocation.

    Add this to your srun/sbatch submission script (in place of a bare
    nccl_check.sh). It launches a small PyTorch FSDP job across all tasks to
    confirm NCCL works. Requires torch in the environment (activate your env,
    or pass --python /path/to/python).

    \b
    Use cases:
      - Verify NCCL and network health before a large distributed run.

    \b
    Inputs:
      --python   Python interpreter with torch (default: python).
      --timeout  Seconds before the check is aborted (default 300).
      --dry-run  Print the srun command instead of running it.
    """
    ntasks = os.environ.get("SLURM_NTASKS_PER_NODE")
    nnodes = os.environ.get("SLURM_NNODES")

    if dry_run:
        tasks = ntasks or "<SLURM_NTASKS_PER_NODE>"
        cmd = ["timeout", str(timeout_s), "srun", f"--ntasks-per-node={tasks}", python_bin, "-u"]
        click.echo(" ".join([*cmd, "<nccl_fsdp_test.py>"]))
        return

    if not (os.environ.get("SLURM_PROCID") and nnodes and ntasks):
        raise click.ClickException(
            "run this inside a Slurm allocation (srun/sbatch); "
            "SLURM_NNODES / SLURM_NTASKS_PER_NODE are not set"
        )

    source = importlib.resources.files("cluster_tools") / "data" / "nccl_fsdp_test.py"
    test_path = pathlib.Path(f"nccl_fsdp_test_{os.environ.get('SLURM_JOB_ID', 'test')}.py")
    test_path.write_text(source.read_text())
    env = {
        "MASTER_ADDR": slurm.first_hostname(),
        "MASTER_PORT": str(_free_port()),
        "WORLD_SIZE": str(int(nnodes) * int(ntasks)),
        "TORCH_CPP_LOG_LEVEL": "ERROR",
    }
    cmd = [
        "timeout",
        str(timeout_s),
        "srun",
        f"--ntasks-per-node={ntasks}",
        python_bin,
        "-u",
        str(test_path),
    ]
    click.echo(f"[NCCL CHECK] Running FSDP test (WORLD_SIZE={env['WORLD_SIZE']})...")
    try:
        code = process.stream(cmd, extra_env=env)
    finally:
        test_path.unlink(missing_ok=True)
    if code != 0:
        raise click.ClickException("NCCL check failed")
    click.echo("NCCL check passed.")
