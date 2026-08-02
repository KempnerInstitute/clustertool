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
    covers the states man scontrol lists RESUME as accepting and Slurm actually
    prints: drained, down, reboot requested or issued, and a registration Slurm
    marked invalid. A powering-down node is left alone rather than fought with
    power save. Each node is listed with its state and the scheduler's reason
    before you confirm, including one named through a hostlist expression, which
    is expanded first so the count is of nodes rather than of arguments. Prompts
    for confirmation unless -y.

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
    if partition and not slurm.partition_exists(partition):
        raise click.ClickException(f"partition '{partition}' does not exist")
    swept = slurm.resumable_nodes(partition) if partition else []
    if partition and not swept and not nodes:
        raise click.ClickException(
            f"no drained, down or invalid-registration nodes in '{partition}'"
        )

    listed: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    if nodes:
        by_name = {name: (name, state, reason) for name, state, reason in swept}
        resolved: dict[str, tuple[str, str, str]] = {}
        unknown = []
        for argument in nodes:
            found = slurm.resumable_nodes_by_name((argument,))
            if not found:
                unknown.append(argument)
            resolved.update(found)
        if unknown:
            raise click.ClickException(
                f"Slurm does not know: {', '.join(unknown)}. A name may be a hostlist "
                "expression such as node[1-4], but it has to resolve to real nodes"
            )
        for name in sorted(resolved):
            listed.append(by_name.get(name) or resolved[name])
            seen.add(name)
    for row in swept:
        if row[0] not in seen:
            listed.append(row)
            seen.add(row[0])
    targets = [row[0] for row in listed]
    nodelist = ",".join(targets)
    click.echo(f"Nodes to resume{f' in {partition}' if partition else ''}:")
    for name, state, reason in listed:
        flags = {flag.strip("*~#!%$@^-") for flag in state.upper().split("+")}
        note = "" if flags & slurm.RESUMABLE_STATES else "  (not in a resumable state)"
        click.echo(f"  {name:<20} {state:<26}{note}  {reason or '-'}")
    click.echo(
        "Resuming a node whose reason is unresolved puts it straight back "
        "into service, where it can start failing jobs again."
    )
    if not yes:
        click.confirm(f"Resume {len(targets)} node(s): {nodelist}?", abort=True)
    process.passthrough(
        ["scontrol", "update", f"NodeName={nodelist}", "State=RESUME"],
        f"failed to resume {nodelist}",
    )
