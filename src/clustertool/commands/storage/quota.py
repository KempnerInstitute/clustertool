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
    """Show a storage quota on any filesystem (via the site quota tool).

    Reports quota and usage for PATH, which selects the filesystem. Use --group for
    a lab's quota or --user for a user's; with neither, the quota tool infers from
    the path. A bare name is prefixed with [storage].path_prefix from the site
    config, and 'home' resolves to your home directory. With --all, report every
    lab directory you belong to as a table; with --fleet LAB, report every LAB*
    directory directly under PATH, by usage. Lab directories usually sit in a
    subdirectory of the filesystem, so point --fleet at that parent, not at the
    mount point.

    Whether --user is honored depends on the site tool: some report per-user usage
    only on filesystems that track it, and fall back to the caller's own figures
    elsewhere. Check the header the tool prints.

    \b
    Use cases:
      - Lab quota on one filesystem: storage quota netscratch -g kempner_dev
      - Your lab dirs at a glance: storage quota --all
      - Fleet view of one root: storage quota holylfs06/LABS --fleet kempner

    \b
    Inputs:
      PATH           Filesystem path, or a bare name the site prefix completes.
      -g, --group    Group/lab name for the lookup.
      -u, --user     User for the lookup (also whose labs --all reports).
      -a, --all      Report every lab directory you belong to as a table.
      --fleet LAB    Report every LAB* dir directly under PATH, by usage.
      -v, --verbose  Show the underlying quota command.
    """
    if group and user:
        raise click.ClickException("give at most one of --group / --user")
    if show_all and (path or group or fleet_keyword is not None):
        raise click.UsageError(
            "--all reports your own lab directories, so it takes neither a PATH, "
            "--group, nor --fleet (--user selects whose labs)"
        )
    if show_all or fleet_keyword is not None:
        _report_table(path, fleet_keyword, user)
        return
    if not path:
        raise click.UsageError("give a PATH, or --all, or --fleet")
    if path == "home":
        target = os.path.expanduser("~")
    else:
        target = path if path.startswith("/") else f"{site.path_prefix()}/{path}"
    process.passthrough(
        storage.quota_cmd(target, group=group, user=user, verbose=verbose),
        f"quota lookup failed for {target}",
    )


def _report_table(path: str | None, fleet_keyword: str | None, user: str | None) -> None:
    """Query quota for a set of lab directories and print a usage table."""
    if fleet_keyword is not None:
        if not fleet_keyword.strip() or "/" in fleet_keyword:
            raise click.UsageError("--fleet takes a directory-name prefix, e.g. --fleet kempner")
        if not path:
            raise click.UsageError(
                "--fleet needs the PATH holding the lab directories, "
                "e.g. holylfs06/LABS --fleet kempner"
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
    problems = []
    read = 0
    for target_path, target_group in targets:
        code, out, err = process.probe(
            storage.quota_cmd(target_path, group=target_group or None), timeout=_QUOTA_TIMEOUT_S
        )
        parsed = storage.parse_quota_row(out) if code == 0 else None
        if parsed:
            read += 1
            rows.append((target_path, *parsed))
            continue
        rows.append((target_path, _failure(code), "-", "-", "-"))
        problems.append(f"{target_path}: {err.strip() or out.strip() or f'exited {code}'}")

    if sort_by_usage:
        rows.sort(
            key=lambda row: (storage.percent_value(row[3]), storage.used_bytes(row[1])),
            reverse=True,
        )
    else:
        rows.sort(key=lambda row: row[0])
    width = max(46, *(len(row[0]) for row in rows))
    click.echo(f"{'STORAGE':<{width}} {'USED':>9} {'QUOTA':>9} {'DISK%':>7} {'FILES%':>7}")
    for target_path, used, quota_value, disk, files in rows:
        click.echo(f"{target_path:<{width}} {used:>9} {quota_value:>9} {disk:>7} {files:>7}")
    click.echo("DISK% and FILES% are usage against the group quota.")
    for problem in problems:
        click.echo(problem, err=True)
    if not read:
        raise click.ClickException(f"no quota could be read for any of the {len(rows)} target(s)")


def _failure(code: int) -> str:
    """Return the cell text for a target whose quota could not be read."""
    if code == 124:
        return "timeout"
    if code == 127:
        return "no tool"
    return "n/a" if code == 0 else "error"
