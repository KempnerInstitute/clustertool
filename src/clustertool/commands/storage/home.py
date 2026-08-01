"""storage home command."""

import os

import click

from clustertool import process
from clustertool.grouping import keywords
from clustertool.storage import humanize_bytes, parse_du_top


@keywords("disk", "space", "du", "homedir")
@click.command("home")
@click.option(
    "-s", "--scan", is_flag=True, help="Also scan home and list its largest subdirectories."
)
@click.option(
    "-n", "--top", "top_n", type=int, default=10, show_default=True, help="Directories to list."
)
@click.option("--ncdu", is_flag=True, help="Launch the interactive ncdu explorer on home instead.")
def home(scan: bool, top_n: int, ncdu: bool) -> None:
    """Show home directory usage, and optionally its largest subdirectories.

    Runs 'df -h ~' to show your home quota (Size), usage, and available space.
    With --scan, also lists the --top N largest subdirectories (default 10) so
    you can find what to clean up. With --ncdu, opens the interactive ncdu
    explorer instead.

    \b
    Use cases:
      - See how much home space you have left (df).
      - Find the biggest directories when near the cap (--scan or --ncdu).

    \b
    Inputs:
      -s, --scan  Also list the largest subdirectories under home.
      -n, --top   How many directories to list with --scan (default 10).
      --ncdu      Launch the interactive ncdu explorer on home.
    """
    home_dir = os.path.expanduser("~")
    if ncdu:
        code = process.stream(["ncdu", home_dir])
        if code:
            raise SystemExit(code)
        return

    process.stream(["df", "-h", home_dir])
    if not scan:
        return
    click.echo()
    click.echo(f"Largest {top_n} directories under {home_dir} (scanning...):")
    output = process.run(["du", "-x", "--block-size=1", "--max-depth=1", home_dir])
    rows = parse_du_top(output, home_dir, top_n)
    if not rows:
        click.echo("  (nothing to show)")
        return
    for size, path in rows:
        click.echo(f"  {humanize_bytes(size):>8}  {path}")
