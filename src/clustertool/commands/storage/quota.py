"""storage quota command."""

import os

import click

from clustertool import process, site, storage
from clustertool.grouping import ToolCommand, keywords

_QUOTA_TIMEOUT_S = 45


@keywords("disk", "space", "limit", "lab", "fleet")
@click.command("quota", cls=ToolCommand, tool_key="quota")
@click.argument("path", required=False)
@click.option("-g", "--group", help="Group/lab name for the quota lookup.")
@click.option("-u", "--user", help="User name for the quota lookup.")
@click.option("-a", "--all", "show_all", is_flag=True, help="Report every lab dir you belong to.")
@click.option(
    "--fleet",
    "fleet_keyword",
    metavar="LAB",
    default=None,
    help="Report every LAB* dir directly under PATH, by usage.",
)
@click.option("-v", "--verbose", is_flag=True, help="Show the underlying quota command.")
def quota(
    path: str | None,
    group: str | None,
    user: str | None,
    show_all: bool,
    fleet_keyword: str | None,
    verbose: bool,
) -> None:
    """Show a storage quota on any filesystem (via the FASRC quota tool).

    Reports quota and usage for PATH, which selects the filesystem: VAST
    (/n/netscratch), Lustre (/n/holylfs06, /n/holystore01, ...), home, and so on.
    Use --group for a lab's quota or --user for a user's; with neither, the quota
    tool infers from the path. A bare name like 'holylfs06' becomes
    '/n/holylfs06', and 'home' resolves to your home directory. With --all,
    report every lab directory you belong to as a table; with --fleet LAB, report
    every LAB* directory directly under PATH, by usage. Lab directories usually
    sit in a subdirectory of the filesystem, so point --fleet at that parent, not
    at the mount point.

    \b
    Use cases:
      - Lab quota on scratch: storage quota netscratch -g kempner_dev
      - Your lab dirs at a glance: storage quota --all
      - Fleet view of one root: storage quota holylfs06/LABS --fleet kempner

    \b
    Inputs:
      PATH           Filesystem path, or a bare name that becomes /n/<name>.
      -g, --group    Group/lab name for the lookup.
      -u, --user     User for the lookup (also whose labs --all reports).
      -a, --all      Report every lab directory you belong to as a table.
      --fleet LAB    Report every LAB* dir directly under PATH, by usage.
      -v, --verbose  Show the underlying quota command.
    """
    if group and user:
        raise click.ClickException("give at most one of --group / --user")
    if show_all or fleet_keyword:
        _report_table(path, fleet_keyword, user)
        return
    if not path:
        raise click.UsageError("give a PATH, or --all, or --fleet")
    if path == "home":
        target = os.path.expanduser("~")
    else:
        target = path if path.startswith("/") else f"{site.path_prefix()}/{path}"
    if process.stream(storage.quota_cmd(target, group=group, user=user, verbose=verbose)):
        raise click.ClickException(f"quota lookup failed for {target}")


def _report_table(path: str | None, fleet_keyword: str | None, user: str | None) -> None:
    """Query quota for a set of lab directories and print a usage table."""
    if fleet_keyword:
        if not path:
            raise click.UsageError(
                "--fleet needs a filesystem PATH, e.g. holylfs06 --fleet kempner"
            )
        root = path if path.startswith("/") else f"{site.path_prefix()}/{path}"
        targets = storage.fleet_targets(root, fleet_keyword)
        if not targets:
            message = f"no directories matching {fleet_keyword}* under {root}"
            prefix = root.rstrip("/") + "/"
            nested = [
                lab_root for lab_root in site.storage_lab_roots() if lab_root.startswith(prefix)
            ]
            if nested:
                message += f"; lab directories on it live under {', '.join(nested)}"
            raise click.ClickException(message)
        sort_by_usage = True
    else:
        username = user or os.environ.get("USER", "")
        targets = storage.lab_targets(storage.user_groups(username), site.storage_lab_roots())
        if not targets:
            raise click.ClickException(f"no lab storage directories found for {username}")
        sort_by_usage = False

    rows = []
    for target_path, target_group in targets:
        code, out, _ = process.probe(
            storage.quota_cmd(target_path, group=target_group or None), timeout=_QUOTA_TIMEOUT_S
        )
        if code == 124:
            rows.append((target_path, "timeout", "-", "-", "-"))
            continue
        parsed = storage.parse_quota_row(out)
        rows.append((target_path, *parsed) if parsed else (target_path, "n/a", "-", "-", "-"))

    if sort_by_usage:
        rows.sort(key=lambda row: storage.percent_value(row[3]), reverse=True)
    else:
        rows.sort(key=lambda row: row[0])
    click.echo(f"{'STORAGE':<46} {'USED':>9} {'QUOTA':>9} {'DISK%':>7} {'FILES%':>7}")
    for target_path, used, quota_value, disk, files in rows:
        click.echo(f"{target_path:<46} {used:>9} {quota_value:>9} {disk:>7} {files:>7}")
    click.echo("DISK% and FILES% are usage against the group quota.")
