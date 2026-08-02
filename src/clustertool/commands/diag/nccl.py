"""diag nccl command."""

import importlib.resources
import os
import pathlib
import shlex
import socket

import click

from clustertool import process, slurm
from clustertool.grouping import keywords


def _tasks_per_node() -> str | None:
    """Return the tasks per node of the surrounding step, or None outside one.

    Slurm sets SLURM_NTASKS_PER_NODE only when --ntasks-per-node was given, per
    the sbatch and salloc man pages, so it is absent from an ordinary allocation.
    SLURM_TASKS_PER_NODE is always set but is a repeat list such as 2(x4), so its
    first count is read and SLURM_NTASKS/SLURM_NNODES is preferred where both are
    present and the layout is even.
    """
    explicit = os.environ.get("SLURM_NTASKS_PER_NODE")
    if explicit and explicit.isdigit():
        return explicit
    ntasks = os.environ.get("SLURM_NTASKS")
    nnodes = os.environ.get("SLURM_NNODES")
    if ntasks and nnodes and ntasks.isdigit() and nnodes.isdigit() and int(nnodes):
        total, count = int(ntasks), int(nnodes)
        if total % count == 0:
            return str(total // count)
    layout = os.environ.get("SLURM_TASKS_PER_NODE", "")
    head = layout.split(",")[0].split("(")[0].strip()
    return head if head.isdigit() else None


def _gpus_per_node(python_bin: str) -> int | None:
    """Return the GPU count this node exposes, or None when it cannot be read."""
    code, out, _ = process.probe(["nvidia-smi", "-L"], timeout=30)
    if code != 0:
        return None
    return sum(1 for line in out.splitlines() if line.strip().startswith("GPU "))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


_TIMEOUT_EXIT = 124
"""Exit code timeout(1) uses when it kills the command it was given."""


@keywords("network", "bandwidth", "allreduce", "collective")
@click.command("nccl")
@click.option(
    "--python",
    "python_bin",
    default="python",
    show_default=True,
    help="Python interpreter with torch to run the test.",
)
@click.option(
    "--timeout",
    "timeout_s",
    type=click.IntRange(min=1),
    default=300,
    show_default=True,
    help="Timeout in seconds.",
)
@click.option("--dry-run", is_flag=True, help="Print the srun command without running it.")
def nccl(python_bin: str, timeout_s: int, dry_run: bool) -> None:
    """Run a multi-node FSDP NCCL sanity check inside a Slurm allocation.

    Add this to your srun/sbatch submission script (in place of a bare
    nccl_check.sh). It launches a small PyTorch FSDP job across all tasks to
    confirm NCCL works. Requires torch in the environment (activate your env,
    or pass --python /path/to/python).

    The test gives each local task one GPU, so it refuses a step whose tasks per
    node does not match the node's GPU count: with fewer tasks the ranks would
    share device 0 and the run would pass without touching NVLink at all.

    Tasks per node is read from SLURM_NTASKS_PER_NODE where Slurm set it, which
    per man sbatch is only when --ntasks-per-node was given, and otherwise
    derived from SLURM_NTASKS and SLURM_NNODES.

    \b
    Use cases:
      - Verify NCCL and network health before a large distributed run.

    \b
    Inputs:
      --python   Python interpreter with torch (default: python).
      --timeout  Seconds before the check is aborted (default 300).
      --dry-run  Print the srun command instead of running it.
    """
    ntasks = _tasks_per_node()
    nnodes = os.environ.get("SLURM_NNODES")

    if dry_run:
        tasks = ntasks or "<tasks per node>"
        cmd = ["timeout", str(timeout_s), "srun", f"--ntasks-per-node={tasks}", python_bin, "-u"]
        click.echo(shlex.join([*cmd, "<nccl_fsdp_test.py>"]))
        return

    missing = [name for name in ("SLURM_PROCID", "SLURM_NNODES") if not os.environ.get(name)]
    if ntasks is None:
        missing.append("the tasks per node")
    if missing:
        raise click.ClickException(
            "run this inside a Slurm allocation (srun/sbatch); this step does not "
            f"report {', '.join(missing)}"
        )
    if not nnodes.isdigit():
        raise click.ClickException(f"SLURM_NNODES is not a number: {nnodes!r}")

    gpus = _gpus_per_node(python_bin)
    if gpus == 0:
        raise click.ClickException(
            "no GPUs on this node; an NCCL check needs at least one per task"
        )
    if gpus is not None and int(ntasks) != gpus:
        raise click.ClickException(
            f"this step runs {ntasks} task(s) per node but the node has {gpus} GPU(s). "
            "The test assigns one GPU per local task, so the ranks would share or "
            "reuse devices and the result would not describe your real run. "
            f"Rerun the step with --ntasks-per-node={gpus}"
        )

    if not process.succeeds([python_bin, "-c", "import torch"]):
        raise click.ClickException(
            f"'{python_bin}' cannot import torch; pass --python /path/to/python, "
            "or activate an environment that has it"
        )

    source = importlib.resources.files("clustertool") / "data" / "nccl_fsdp_test.py"
    staging = pathlib.Path(os.environ.get("SLURM_SUBMIT_DIR") or pathlib.Path.cwd())
    test_path = (staging / f"nccl_fsdp_test_{os.environ.get('SLURM_JOB_ID', 'test')}.py").resolve()
    try:
        test_path.write_text(source.read_text())
    except OSError as exc:
        raise click.ClickException(
            f"cannot stage the test script in {staging}: {exc}. Every task must be "
            "able to read it, so run from a directory on a shared filesystem"
        ) from exc
    try:
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
        code = process.stream(cmd, extra_env=env)
    finally:
        test_path.unlink(missing_ok=True)
    if code == _TIMEOUT_EXIT:
        raise click.ClickException(
            f"the NCCL check did not finish within {timeout_s}s. A rank that never "
            "joins leaves init_process_group waiting, so check that every task "
            "started and that the ranks agree on WORLD_SIZE; raise --timeout if the "
            "run is simply slow"
        )
    if code != 0:
        raise click.ClickException(f"NCCL check failed (exit {code})")
    click.echo("NCCL check passed.")
