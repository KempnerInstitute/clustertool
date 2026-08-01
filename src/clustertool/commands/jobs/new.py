"""jobs new command."""

from pathlib import Path

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords


def _build_script(
    gpu_type: str,
    gpus: int,
    nodes: int,
    time_limit: str,
    account: str,
    name: str,
    cpus_per_gpu: int | None,
    mem_per_gpu: int | None,
) -> str:
    """Return an sbatch script for a GPU job, sized to the per-GPU limits.

    A partition with no configured ratio and no override gets no cpus-per-task or
    mem line.
    """
    partition = slurm.GPU_TYPE_PARTITION[gpu_type.lower()]
    default_cpu, default_mem = slurm.PARTITION_LIMITS.get(partition, (None, None))
    lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={name}",
        f"#SBATCH --partition={partition}",
        f"#SBATCH --account={account}",
        f"#SBATCH --nodes={nodes}",
        f"#SBATCH --gres=gpu:{gpus}",
    ]
    cpu_each = cpus_per_gpu or default_cpu
    mem_each = mem_per_gpu or default_mem
    if cpu_each:
        lines.append(f"#SBATCH --cpus-per-task={cpu_each * gpus}")
    if mem_each:
        lines.append(f"#SBATCH --mem={mem_each * gpus}")
    lines += [
        f"#SBATCH --time={time_limit}",
        "#SBATCH --output=%x_%j.out",
        "",
        "# Your commands below.",
        "",
    ]
    return "\n".join(lines) + "\n"


@keywords("submit", "sbatch", "template", "generate", "wizard", "create")
@click.command("new")
@click.option(
    "--gpu-type",
    type=click.Choice(list(slurm.GPU_TYPE_PARTITION)),
    prompt="GPU type",
    help="GPU type (selects the partition and per-GPU CPU and memory).",
)
@click.option(
    "-A",
    "--account",
    prompt=True,
    help="Fairshare account to charge.",
    shell_complete=completion.complete_accounts,
)
@click.option("--gpus", type=int, default=1, show_default=True, help="GPUs per node.")
@click.option("--nodes", type=int, default=1, show_default=True, help="Number of nodes.")
@click.option(
    "-t", "--time", "time_limit", default="0-04:00", show_default=True, help="Time limit (D-HH:MM)."
)
@click.option("-J", "--name", default="job", show_default=True, help="Job name.")
@click.option("--cpus-per-gpu", type=int, default=None, help="Override CPUs per GPU.")
@click.option("--mem-per-gpu", type=int, default=None, help="Override memory per GPU in MB.")
@click.option("-o", "--output", default=None, help="Write the script to this file.")
@click.option("--submit", is_flag=True, help="Submit the generated script with sbatch.")
def new(
    gpu_type: str,
    account: str,
    gpus: int,
    nodes: int,
    time_limit: str,
    name: str,
    cpus_per_gpu: int | None,
    mem_per_gpu: int | None,
    output: str | None,
    submit: bool,
) -> None:
    """Build a GPU sbatch script, then print, save, or submit it.

    This writes a GPU job: it always requests a GPU and targets a GPU partition.
    Prompts for the GPU type and account if not given, sizes CPUs and memory to
    the partition's enforced per-GPU limits, and writes a correct sbatch header.
    A partition with no configured ratio and no override gets no cpus-per-task or
    mem line, leaving Slurm to apply its own defaults. Prints the script by
    default; use -o to save it or --submit to submit it.

    \b
    Use cases:
      - Generate a correct sbatch header without memorizing the conventions.
      - Submit a single-node or multi-node GPU job in one step.

    \b
    Inputs:
      --gpu-type       A GPU type your site defines under [gpu_types]; the usage
                       line above lists the valid values (prompted if omitted).
      -A, --account    Fairshare account (prompted if omitted).
      --gpus           GPUs per node (default 1).
      --nodes          Number of nodes (default 1).
      -t, --time       Time limit D-HH:MM (default 0-04:00).
      -J, --name       Job name (default job).
      --cpus-per-gpu   Override CPUs per GPU.
      --mem-per-gpu    Override memory per GPU in MB.
      -o, --output     Write the script to a file.
      --submit         Submit the script with sbatch.
    """
    script = _build_script(
        gpu_type, gpus, nodes, time_limit, account, name, cpus_per_gpu, mem_per_gpu
    )
    if output:
        Path(output).write_text(script)
        click.echo(f"Wrote {output}")
    if submit:
        click.echo(process.run(["sbatch"], input_text=script).strip())
    if not output and not submit:
        click.echo(script, nl=False)
