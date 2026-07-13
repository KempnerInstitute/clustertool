"""Diagnostic commands."""

import os
import shutil

import click

from cluster_tools import process, slurm


@click.group()
def diag() -> None:
    """Run cluster diagnostics."""


@diag.command("nccl")
@click.argument("node")
@click.option("--binary", help="Path to the nccl-tests all_reduce_perf binary.")
@click.option("--partition", help="Partition to run in (default: the node's first partition).")
@click.option(
    "--time",
    "time_limit",
    default="00:05:00",
    show_default=True,
    help="Slurm time limit for the test job.",
)
@click.option("--dry-run", is_flag=True, help="Print the srun command without running it.")
def nccl(
    node: str, binary: str | None, partition: str | None, time_limit: str, dry_run: bool
) -> None:
    """Run a single-node NCCL bandwidth test on a GPU node.

    Checks that NODE is a GPU node, then launches the nccl-tests all_reduce_perf
    benchmark on it with one rank per GPU. Errors if NODE has no GPUs. Running
    the test (not --dry-run) requires the nccl-tests binary: build it, load a
    module that provides it, set NCCL_TESTS_PATH, or pass --binary.

    \b
    Use cases:
      - Sanity-check NCCL and intra-node GPU bandwidth on a node.
      - Confirm a node's GPUs communicate before a large run.

    \b
    Inputs:
      NODE         GPU node name (e.g. holygpu8a11101).
      --binary     Path to all_reduce_perf (overrides lookup).
      --partition  Partition to run in (default: the node's first partition).
      --time       Slurm time limit (default 00:05:00).
      --dry-run    Print the srun command instead of running it.
    """
    info = slurm.node_info(node)
    if info["gpus"] < 1:
        raise click.ClickException(f"'{node}' is not a GPU node")
    resolved = binary or _find_nccl_binary()
    if not resolved and not dry_run:
        raise click.ClickException(
            "nccl-tests 'all_reduce_perf' not found; build it, load a module that "
            "provides it, set NCCL_TESTS_PATH, or pass --binary"
        )
    if not partition and info["partitions"]:
        partition = info["partitions"][0]
    command = _srun_command(
        info["name"], info["gpus"], resolved or "all_reduce_perf", partition, time_limit
    )
    if dry_run:
        click.echo(" ".join(command))
        return
    click.echo(f"Running NCCL bandwidth test on {info['name']} ({info['gpus']} GPU)...")
    code = process.stream(command)
    if code:
        raise SystemExit(code)


def _find_nccl_binary() -> str | None:
    """Locate the nccl-tests all_reduce_perf binary."""
    root = os.environ.get("NCCL_TESTS_PATH")
    if root:
        candidate = os.path.join(root, "all_reduce_perf")
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("all_reduce_perf")


def _srun_command(
    node: str, gpus: int, binary: str, partition: str | None, time_limit: str
) -> list[str]:
    """Build the srun command for a single-node NCCL bandwidth test."""
    command = [
        "srun",
        f"--nodelist={node}",
        "--nodes=1",
        "--ntasks=1",
        f"--gpus-per-node={gpus}",
        f"--time={time_limit}",
    ]
    if partition:
        command.append(f"--partition={partition}")
    command += [binary, "-b", "8", "-e", "128M", "-f", "2", "-g", str(gpus)]
    return command
