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

    Give explicit node names, or --partition to sweep a whole partition. The sweep
    covers every state scontrol's RESUME accepts: drained, draining, down, failing,
    and rebooting. Each node is listed with its state and the scheduler's reason
    before you confirm. Prompts for confirmation unless -y.

    \b
    Use cases:
      - Bring auto-drained requeue nodes back after a transient issue.

    \b
    Inputs:
      NODE...          One or more node names to resume.
      -p, --partition  Resume every resumable node in this partition.
      -y, --yes        Skip the confirmation prompt.
    """
    if not nodes and not partition:
        raise click.UsageError("Give one or more NODEs, or --partition.")
    swept = slurm.resumable_nodes(partition) if partition else []
    if partition and not swept and not nodes:
        raise click.ClickException(f"no drained, down or failing nodes in '{partition}'")
    listed = list(swept)
    if nodes:
        by_name = {name: (name, state, reason) for name, state, reason in swept}
        known = slurm.resumable_nodes_by_name(nodes)
        listed = [by_name.get(name) or known.get(name) or (name, "?", "") for name in nodes] + [
            row for row in swept if row[0] not in nodes
        ]
    targets = [row[0] for row in listed]
    nodelist = ",".join(targets)
    click.echo(f"Nodes to resume{f' in {partition}' if partition else ''}:")
    for name, state, reason in listed:
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
