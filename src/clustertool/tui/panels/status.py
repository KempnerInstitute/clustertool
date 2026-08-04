"""The status bar along the bottom of the dashboard."""

import datetime
from collections.abc import Callable

from rich.cells import cell_len
from textual.widgets import Static

from clustertool.tui import data

CLOCK_FORMAT = "%a %Y-%m-%d %H:%M"
GAP = "   "

KEYS = "? keys   Q quit"
"""The two keys a first-time reader needs, kept at the right of the bar.

Every binding is in the help overlay, but the overlay is itself behind a key, so how
to leave and how to reach the rest have to be visible without asking.
"""


def fit(identity: data.Identity, stamp: str, width: int) -> str:
    """Return the widest status line that fits, shedding the least useful part first.

    The bar is one row, so a line too long for it wraps and is clipped. Each rung of
    the ladder adds one field to the rung beneath it, so widening the terminal can
    never remove something that was already shown.

    Widths are counted in display cells rather than code points, since a full name in
    a script two cells wide fits by count and then wraps.
    """
    who = identity
    name = f" ({who.full_name})" if who.full_name else ""
    ladder = [
        stamp,
        f"{who.user}{GAP}{stamp}",
        f"{who.user} @ {who.host}{GAP}{stamp}",
        f"{who.user}{name} @ {who.host}{GAP}{stamp}",
        f"{who.user}{name} @ {who.host}{GAP}{stamp}{GAP}{KEYS}",
        f"{who.user}{name} @ {who.host}{GAP}{who.site_name}{GAP}{stamp}{GAP}{KEYS}",
    ]
    for line in reversed(ladder):
        if cell_len(line) <= width:
            if not line.endswith(KEYS):
                return line
            head = line[: -len(KEYS)].rstrip()
            return head + " " * max(width - cell_len(KEYS) - cell_len(head), 0) + KEYS
    return _cells(stamp, width)


def _cells(text: str, width: int) -> str:
    """Cut text to a number of display cells rather than of code points.

    Reached only when the clock alone is wider than the bar.
    """
    out = ""
    for char in text:
        if cell_len(out + char) > width:
            break
        out += char
    return out


class StatusBar(Static):
    """Who you are, where you are, and the time, kept visible at all times.

    Markup is off: the full name comes from the GECOS field and the site name from a
    config file, so a bracket in either would be parsed as a style tag.
    """

    def __init__(
        self,
        identity: data.Identity,
        clock: Callable[[], datetime.datetime] = datetime.datetime.now,
    ) -> None:
        super().__init__(id="status", markup=False)
        self._identity = identity
        self._clock = clock

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)

    def render(self) -> str:
        stamp = self._clock().strftime(CLOCK_FORMAT)
        return fit(self._identity, stamp, self.size.width or 80)
