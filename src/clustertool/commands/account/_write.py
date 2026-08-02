"""Shared validation and association listing for the account write commands."""

import re

import click

from clustertool import qos as qoslib
from clustertool import site, slurm


def check_names(**values: str) -> None:
    """Reject a name sacctmgr would read as a list, which would widen the write.

    man sacctmgr defines account, user and cluster specifications as
    comma-separated lists, so a stray comma turns one intended change into
    several. A value of None is a flag that was not given and is skipped.
    """
    for label, value in values.items():
        if value is None:
            continue
        if not qoslib.valid_name(value):
            raise click.ClickException(
                f"invalid {label.upper()} {value!r}: a name cannot contain a comma or "
                "whitespace, which sacctmgr would read as a list"
            )


_FS_USE_PARENT = 0x7FFFFFFF
"""The raw-shares value Slurm reads as 'inherit the parent's', per slurmdb.h."""


def check_fairshare(share: str) -> None:
    """Reject a fairshare value sacctmgr would not accept as raw shares.

    Slurm stores the shares as a uint32 and reserves 0x7FFFFFFF to mean parent,
    so a literal 2147483647 would silently become parent rather than that many
    shares. Digits are matched as ASCII, since a non-ASCII digit passes
    str.isdigit() and reaches sacctmgr as text it cannot read.
    """
    if share.lower() == "parent":
        return
    if not re.fullmatch(r"[0-9]+", share):
        raise click.ClickException(
            f"invalid fairshare {share!r}: give an integer number of raw shares, "
            "or 'parent' to inherit the account's"
        )
    if int(share) >= _FS_USE_PARENT:
        raise click.ClickException(
            f"fairshare {share} is at or above {_FS_USE_PARENT}, which Slurm reads "
            "as 'parent' rather than as that many shares; give a smaller number, or "
            "'parent' if that is what you mean"
        )


def cluster_scope(cluster: str | None) -> str:
    """Return the cluster= specification every write is scoped to.

    man sacctmgr gives the default for a user specification as all clusters in the
    system, so an unscoped write acts on every cluster at a multi-cluster site.
    """
    return f"cluster={cluster or site.qos_cluster()}"


def check_targets(user: str, account: str, cluster: str | None) -> None:
    """Fail with the real cause when a read against these would return no rows.

    sacctmgr answers a query naming a user, an account or a cluster that does not
    exist with an empty result and exit 0, so all three read as "this user has no
    association with this account" and the cluster is never even mentioned.
    """
    if cluster and not qoslib.cluster_exists(cluster):
        raise click.ClickException(f"no such cluster: {cluster}")
    if not slurm.user_exists(user):
        raise click.ClickException(f"no such user on this host: {user}")
    if not slurm.account_exists(account):
        raise click.ClickException(f"account '{account}' does not exist")


def where(user: str, account: str, cluster: str | None) -> str:
    """Return a phrase naming everything a write is scoped to, for a prompt."""
    return f"{user} in {account} on {cluster_scope(cluster).split('=', 1)[1]}"


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
