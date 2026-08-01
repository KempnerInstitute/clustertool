"""Shared validation and association listing for the account write commands."""

import click

from clustertool import qos as qoslib
from clustertool import site


def check_names(**values: str) -> None:
    """Reject a name sacctmgr would read as a list, which would widen the write.

    man sacctmgr defines account and user specifications as comma-separated lists,
    so a stray comma turns one intended change into several.
    """
    for label, value in values.items():
        if not qoslib.valid_name(value):
            raise click.ClickException(
                f"invalid {label.upper()} {value!r}: a name cannot contain a comma or "
                "whitespace, which sacctmgr would read as a list"
            )


def check_fairshare(share: str) -> None:
    """Reject a fairshare value sacctmgr would not accept as raw shares."""
    if share != "parent" and not share.isdigit():
        raise click.ClickException(
            f"invalid fairshare {share!r}: give an integer number of raw shares, "
            "or 'parent' to inherit the account's"
        )


def cluster_scope(cluster: str | None) -> str:
    """Return the cluster= specification every write is scoped to.

    man sacctmgr gives the default for a user specification as all clusters in the
    system, so an unscoped write acts on every cluster at a multi-cluster site.
    """
    return f"cluster={cluster or site.qos_cluster()}"


def associations(user: str, account: str, cluster: str | None) -> list[tuple[str, str]]:
    """Return (partition, qos) for each association a user holds in an account.

    An empty partition is the base association. Raises if the query fails, so a
    write is never described against a read that did not happen.
    """
    rows = []
    for line in qoslib.show_assoc_rows(user, account, cluster):
        parts = line.split("|")
        if len(parts) == 2:
            rows.append((parts[0].strip(), parts[1].strip()))
    return rows


def describe(rows: list[tuple[str, str]]) -> None:
    """Print the associations a write will touch, so the prompt is not a guess."""
    for partition, qos_list in rows:
        where = partition or "(no partition)"
        click.echo(f"  {where:<28} QoS: {qos_list or '-'}")
