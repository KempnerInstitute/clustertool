"""storage lfs-stripe command."""

import click

from cluster_tools import process
from cluster_tools.grouping import keywords


@keywords("lustre", "layout")
@click.command("lfs-stripe")
@click.argument("path")
@click.option(
    "-c", "--count", type=int, default=None, help="Set the stripe count for new files in PATH."
)
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def lfs_stripe(path: str, count: int | None, yes: bool) -> None:
    """Show or set Lustre striping for a path (via lfs).

    Without --count, print the current stripe layout (lfs getstripe). With
    --count, set the stripe count for newly created files under PATH
    (lfs setstripe); existing files are not restriped. Use 8 to 16 for large
    multi-GB or TB files. Setting a count changes the default for everyone who
    writes new files there, so it prompts for confirmation unless -y.

    \b
    Use cases:
      - Check how a directory is striped across Lustre targets.
      - Widen striping before writing very large files for throughput.

    \b
    Inputs:
      PATH         A path on a Lustre filesystem (e.g. /n/holylfs06/...).
      -c, --count  Stripe count to set for new files under PATH.
      -y, --yes    Skip the confirmation prompt.
    """
    if count is None:
        cmd = ["lfs", "getstripe", path]
    else:
        if not yes:
            click.confirm(
                f"Set stripe count {count} for new files under {path}?",
                abort=True,
            )
        cmd = ["lfs", "setstripe", "-c", str(count), path]
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
