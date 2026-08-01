"""nodes resume command."""

import click

from clustertool import completion, process, slurm
from clustertool.grouping import admin, keywords


@admin
@keywords("undrain", "restore", "fix", "enable")
@click.command("resume")
@click.argument("nodes", nargs=-1, metavar="[NODE...]")
@click.option(
    "-p",
    "--partition",
    default=None,
    help="Resume drained nodes in this partition.",
    shell_complete=completion.complete_partitions,
)
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def resume(nodes: tuple[str, ...], partition: str | None, yes: bool) -> None:
    """Return drained or down nodes to service (via scontrol). Slurm or system admin only.

    Give explicit node names, or --partition to resume every drained node in a
    partition. Prompts for confirmation unless -y.

    \b
    Use cases:
      - Bring auto-drained requeue nodes back after a transient issue.

    \b
    Inputs:
      NODE...          One or more node names to resume.
      -p, --partition  Resume all drained nodes in this partition.
      -y, --yes        Skip the confirmation prompt.
    """
    targets = list(nodes)
    swept = slurm.drained_nodes(partition) if partition else []
    targets += [name for name, _, _ in swept]
    if not targets:
        raise click.UsageError("Give one or more NODEs, or --partition.")
    nodelist = ",".join(targets)
    if swept:
        click.echo(f"Drained nodes in {partition}:")
        for name, state, reason in swept:
            note = " (not responding)" if state.endswith("*") else ""
            click.echo(f"  {name:<20} {state:<12}{note}  {reason or '-'}")
        click.echo(
            "Resuming a node whose reason is unresolved puts it straight back "
            "into service, where it can start failing jobs again."
        )
    if not yes:
        click.confirm(f"Resume {len(targets)} node(s): {nodelist}?", abort=True)
    if process.stream(["scontrol", "update", f"NodeName={nodelist}", "State=RESUME"]):
        raise click.ClickException(f"failed to resume {nodelist}")
