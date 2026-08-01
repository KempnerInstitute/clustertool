"""storage lfs-stripe command."""

import os

import click

from clustertool import process, site, storage
from clustertool.grouping import ToolCommand, keywords

_ALL_OSTS = -1
_FILESYSTEM_DEFAULT = 0


@keywords("lustre", "layout")
@click.command("lfs-stripe", cls=ToolCommand, tool_key="lfs")
@click.argument("path")
@click.option(
    "-c", "--count", type=int, default=None, help="Set the stripe count for new files in PATH."
)
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def lfs_stripe(path: str, count: int | None, yes: bool) -> None:
    """Show or set Lustre striping for a path (via lfs).

    Without --count, print the layout of PATH itself and not of anything inside it
    (lfs getstripe -d). With --count, set the stripe count for newly created files
    under PATH (lfs setstripe); existing files are not restriped.

    A count spreads each new file over that many OSTs, so it trades throughput on
    large files against more metadata work and wider exposure to a single OST
    going away. Match it to the file size: one stripe suits ordinary files, and a
    file in the hundreds of GB or larger benefits from many. Two counts are
    special, as lfs-setstripe defines them: 0 restores the filesystem-wide default
    rather than setting zero stripes, and -1 stripes over every available OST. A
    count above the number of OSTs is refused, since lfs would silently clamp it;
    use lfs setstripe -C directly if you really want more than one stripe per OST.

    Setting a count changes the default for everyone who writes new files there,
    so it prompts for confirmation unless -y. Lustre allows it only on a directory
    you own: on one you merely have group write access to it fails with Operation
    not permitted.

    \b
    Use cases:
      - Check how a directory is striped across Lustre targets.
      - Widen striping before writing very large files for throughput.

    \b
    Inputs:
      PATH         A path on a Lustre filesystem.
      -c, --count  Stripe count for new files under PATH, or 0 / -1.
      -y, --yes    Skip the confirmation prompt.
    """
    lfs = site.tool("lfs")
    if not os.path.exists(path):
        raise click.ClickException(f"path not found: {path}")
    if count is None:
        process.passthrough([lfs, "getstripe", "-d", path], f"'{lfs} getstripe' failed for {path}")
        return

    osts = storage.lustre_ost_count(path)
    if count < _ALL_OSTS:
        raise click.ClickException(
            f"invalid --count {count}: give a positive count, 0 for the filesystem "
            "default, or -1 for every OST"
        )
    if osts and count > osts:
        raise click.ClickException(
            f"invalid --count {count}: {path} has {osts} OSTs, and lfs would clamp "
            f"the count to that. Use -c {osts} or -c -1 for all of them"
        )
    if not yes:
        click.confirm(_prompt(path, count, osts), abort=True)
    process.passthrough(
        [lfs, "setstripe", "-c", str(count), path], f"'{lfs} setstripe' failed for {path}"
    )


def _prompt(path: str, count: int, osts: int) -> str:
    """Return the confirmation question, spelling out what the special counts mean."""
    if count == _FILESYSTEM_DEFAULT:
        return f"Reset new files under {path} to the filesystem default stripe count?"
    if count == _ALL_OSTS:
        spread = f"all {osts} OSTs" if osts else "every available OST"
        return f"Stripe new files under {path} across {spread}?"
    return f"Set stripe count {count} for new files under {path}?"
