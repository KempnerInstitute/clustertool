"""account remove-user command."""

import click

from clustertool import completion, process
from clustertool.commands.account import _write
from clustertool.grouping import admin, keywords


@admin
@keywords("revoke", "kick", "delete", "unenroll")
@click.command("remove-user")
@click.argument("user")
@click.argument("account", shell_complete=completion.complete_accounts)
@click.option(
    "-p",
    "--partition",
    default=None,
    help="Remove only the association on this partition.",
    shell_complete=completion.complete_partitions,
)
@click.option("-c", "--cluster", default=None, help="Slurm cluster (default: the site cluster).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def remove_user(
    user: str, account: str, partition: str | None, cluster: str | None, yes: bool
) -> None:
    """Remove a user's associations with an account (via sacctmgr).

    A user can hold several associations in one account: a base one, plus one per
    partition, each with its own QoS list. Without --partition this removes all of
    them, so a priority QoS granted on a single partition goes too; every
    association is listed before you confirm. Give --partition to remove just that
    one. The user's other accounts are untouched. Prompts for confirmation unless
    -y.

    Slurm operator, or a coordinator of the account; a site that sets
    DisableCoordDBD in slurmdbd.conf restricts this to operators.

    \b
    Use cases:
      - Remove a former member from a lab's Slurm account.
      - Drop one partition's association while keeping the account membership.

    \b
    Inputs:
      USER             Username to remove.
      ACCOUNT          Slurm account to remove them from.
      -p, --partition  Remove only the association on this partition.
      -c, --cluster    Slurm cluster (default: the site cluster).
      -y, --yes        Skip the confirmation prompt.
    """
    _write.check_names(user=user, account=account)
    if partition is not None:
        _write.check_names(partition=partition)
    rows = _write.associations(user, account, cluster)
    if not rows:
        raise click.ClickException(f"{user} has no association with account {account}")
    if partition is not None:
        rows = [row for row in rows if row[0] == partition]
        if not rows:
            raise click.ClickException(
                f"{user} has no association with account {account} on partition {partition}"
            )

    click.echo(f"Associations to remove for {user} in {account}:")
    _write.describe(rows)
    if not yes:
        click.confirm(f"Remove {len(rows)} association(s)?", abort=True)
    cmd = ["sacctmgr", "-i", "remove", "user", user, f"account={account}"]
    cmd.append(_write.cluster_scope(cluster))
    if partition is not None:
        cmd.append(f"partition={partition}")
    process.passthrough(cmd, f"failed to remove {user} from {account}")
