"""storage lustre command."""

import getpass
import grp
import os

import click

from cluster_tools import process
from cluster_tools.storage import LUSTRE_MOUNT, lustre_quota_cmd


@click.command("lustre")
@click.argument("name", required=False)
@click.option(
    "--user",
    "as_user",
    is_flag=True,
    help="Report a user quota (-hu) instead of a group/lab quota (-hg).",
)
@click.option(
    "--path",
    "-p",
    default=LUSTRE_MOUNT,
    show_default=True,
    help="Lustre mount (e.g. /n/holylfs06, /n/holystore01; a bare name becomes /n/<name>).",
)
def lustre(name: str | None, as_user: bool, path: str) -> None:
    """Show a lab (group) or user storage quota on a Lustre filesystem.

    Runs 'lfs quota -hg NAME PATH' for a group (default), or 'lfs quota -hu NAME
    PATH' with --user. NAME defaults to your primary group, or your username with
    --user.

    \b
    Use cases:
      - Check a lab's Lustre quota: storage lustre kempner_dev
      - Check your own usage: storage lustre --user
      - On another filesystem: storage lustre kempner_dev --path /n/holystore01

    \b
    Inputs:
      NAME    Group (lab) or user name. Defaults to your primary group, or your
              username with --user.
      --user  Report a user quota (-hu) instead of a group quota (-hg).
      --path  Lustre mount point (a bare name like holystore01 becomes
              /n/holystore01).
    """
    if name is None:
        name = getpass.getuser() if as_user else grp.getgrgid(os.getgid()).gr_name
    mount = path if path.startswith("/") else f"/n/{path}"
    code = process.stream(lustre_quota_cmd(name, mount, user=as_user))
    if code:
        raise SystemExit(code)
