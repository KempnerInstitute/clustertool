"""Storage commands."""

import click

from cluster_tools import process
from cluster_tools.storage import lustre_quota_cmd, vast_quota_cmd


@click.group()
def storage() -> None:
    """Inspect storage quotas."""


@storage.command("quota")
@click.argument("account")
@click.option(
    "--filesystem",
    "-f",
    type=click.Choice(["vast", "lustre"]),
    default="vast",
    show_default=True,
    help="Filesystem to report on.",
)
def quota(account: str, filesystem: str) -> None:
    """Show an account's storage quota on VAST or Lustre.

    \b
    Use cases:
      - Check a lab's scratch usage on VAST (/n/netscratch).
      - Check a lab's Lustre group quota (/n/holylfs06).

    \b
    Inputs:
      ACCOUNT           Account/group name (e.g. kempner_dev).
      -f, --filesystem  vast (default) or lustre.
    """
    cmd = vast_quota_cmd(account) if filesystem == "vast" else lustre_quota_cmd(account)
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
