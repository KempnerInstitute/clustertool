"""nodes reservations command."""

import click

from cluster_tools import process


@click.command("reservations")
def reservations() -> None:
    """List active reservations on the cluster (via scontrol).

    \b
    Use cases:
      - See time-boxed reserved compute and the nodes it holds.
      - Find a reservation name to submit into with --reservation.
    """
    code = process.stream(["scontrol", "show", "reservation"])
    if code:
        raise SystemExit(code)
