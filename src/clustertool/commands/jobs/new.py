"""jobs new command."""

import re
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
    """Return an sbatch script for a GPU job, sized from the site per-GPU policy.

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
        "#SBATCH --ntasks-per-node=1",
    ]
    cpu_each = cpus_per_gpu if cpus_per_gpu is not None else default_cpu
    mem_each = mem_per_gpu if mem_per_gpu is not None else default_mem
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


_DIRECTIVE_VALUE = re.compile(r"^[A-Za-z0-9._+:@-]+$")


def _check_value(option: str, value: str) -> None:
    """Reject a value sbatch cannot read as one directive argument.

    Per man sbatch a #SBATCH line is read directly by Slurm, so a space ends the
    argument and a newline both injects a script line and stops every later
    directive from being processed.
    """
    if not _DIRECTIVE_VALUE.match(value or ""):
        raise click.ClickException(
            f"{option} must be a single word of letters, digits, and . _ + : @ - ; "
            f"Slurm reads a #SBATCH line directly, so {value!r} would not survive it"
        )


@keywords("submit", "sbatch", "template", "generate", "wizard", "create")
@click.command("new")
@click.option(
    "--gpu-type",
    type=click.Choice(list(slurm.GPU_TYPE_PARTITION), case_sensitive=False),
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
@click.option(
    "--gpus", type=click.IntRange(min=1), default=1, show_default=True, help="GPUs per node."
)
@click.option(
    "--nodes", type=click.IntRange(min=1), default=1, show_default=True, help="Number of nodes."
)
@click.option(
    "-t", "--time", "time_limit", default="0-04:00", show_default=True, help="Time limit (D-HH:MM)."
)
@click.option("-J", "--name", default="job", show_default=True, help="Job name.")
@click.option(
    "--cpus-per-gpu", type=click.IntRange(min=1), default=None, help="Override CPUs per GPU."
)
@click.option(
    "--mem-per-gpu", type=click.IntRange(min=1), default=None, help="Override memory per GPU in MB."
)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write the generated script to this file.",
)
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
    Prompts for the GPU type and account if not given, then sizes CPUs and memory
    from the per-GPU policy your site sets under [partitions.limits]. A partition
    with no configured ratio and no override gets no cpus-per-task or mem line,
    leaving Slurm to apply its own defaults. Prints the script by default; use -o
    to save it or --submit to submit it.

    \b
    Use cases:
      - Generate a correct sbatch header without memorizing the conventions.
      - Submit a single-node or multi-node GPU job in one step.

    \b
    Inputs:
      --gpu-type       A GPU type your site defines under [gpu_types]; the
                       Options list above shows the valid values (prompted if
                       omitted).
      -A, --account    Fairshare account (prompted if omitted).
      --gpus           GPUs per node (default 1).
      --nodes          Number of nodes (default 1).
      -t, --time       Time limit D-HH:MM (default 0-04:00).
      -J, --name       Job name (default job).
      --cpus-per-gpu   Override CPUs per GPU.
      --mem-per-gpu    Override memory per GPU in MB.
      -o, --output     Write the generated script to a file, replacing it if it
                       already exists.
      --submit         Submit the script with sbatch.
    """
    _check_value("-J/--name", name)
    _check_value("-A/--account", account)
    _check_value("-t/--time", time_limit)
    partition = slurm.GPU_TYPE_PARTITION[gpu_type.lower()]
    ceiling_cpu, ceiling_mem = slurm.PARTITION_LIMITS.get(partition, (None, None))
    for option, given, ceiling, unit in (
        ("--cpus-per-gpu", cpus_per_gpu, ceiling_cpu, "CPU"),
        ("--mem-per-gpu", mem_per_gpu, ceiling_mem, "MiB"),
    ):
        if given is not None and ceiling and given > ceiling:
            raise click.ClickException(
                f"{option} {given} is above the {ceiling} {unit} per GPU that "
                f"{partition} allows, so the job would be rejected at submission"
            )
    if not slurm.PARTITION_LIMITS.get(partition) and cpus_per_gpu is None and mem_per_gpu is None:
        click.echo(
            f"note: no per-GPU policy is configured for {partition}, so the script "
            "requests no CPUs or memory and Slurm applies its own defaults",
            err=True,
        )
    script = _build_script(
        gpu_type, gpus, nodes, time_limit, account, name, cpus_per_gpu, mem_per_gpu
    )
    if output:
        try:
            Path(output).write_text(script)
        except OSError as exc:
            raise click.ClickException(f"cannot write {output}: {exc}") from exc
        click.echo(f"Wrote {output}")
    if submit:
        code, out, err = process.probe(["sbatch"], input_text=script)
        if code == 127:
            raise click.ClickException("'sbatch' not found on this host")
        if code:
            raise click.ClickException(err.strip() or f"sbatch exited {code}")
        click.echo(out.strip())
    if not output and not submit:
        click.echo(script, nl=False)
