"""nodes resume command."""

import click

from cluster_tools import process, slurm


@click.command("resume")
@click.argument("nodes", nargs=-1, metavar="[NODE...]")
@click.option("-p", "--partition", default=None, help="Resume drained nodes in this partition.")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def resume(nodes: tuple[str, ...], partition: str | None, yes: bool) -> None:
    """Return drained or down nodes to service (via scontrol). Operator only.

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
    if partition:
        targets += slurm.drained_nodes(partition)
    if not targets:
        raise click.UsageError("Give one or more NODEs, or --partition.")
    nodelist = ",".join(targets)
    if not yes:
        click.confirm(f"Resume {len(targets)} node(s): {nodelist}?", abort=True)
    code = process.stream(["scontrol", "update", f"NodeName={nodelist}", "State=RESUME"])
    if code:
        raise SystemExit(code)
