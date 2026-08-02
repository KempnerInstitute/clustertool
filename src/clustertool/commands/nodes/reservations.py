"""nodes reservations command."""

import click

from clustertool import process
from clustertool.grouping import keywords


@keywords("reserved", "booked", "reservation")
@click.command("reservations")
def reservations() -> None:
    """List the cluster's reservations and the nodes they hold (via scontrol).

    Shows every reservation Slurm knows about, current and scheduled: State=ACTIVE
    is holding nodes now, State=INACTIVE starts at its StartTime.

    \b
    Use cases:
      - See time-boxed reserved compute and the nodes it holds.
      - Find a reservation name to submit into with --reservation.
      - Check for upcoming maintenance windows before planning a long run.
    """
    process.passthrough(["scontrol", "show", "reservation"], "'scontrol show reservation' failed")
