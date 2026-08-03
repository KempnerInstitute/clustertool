"""The status bar along the bottom of the dashboard."""

import datetime
from collections.abc import Callable

from textual.widgets import Static

from clustertool.tui import data

CLOCK_FORMAT = "%a %Y-%m-%d %H:%M"
GAP = "   "

KEYS = "? keys   Q quit"
"""The two keys a first-time reader needs, kept at the right of the bar.

Every binding is in the help overlay, but the overlay is itself behind a key, so
nothing on screen said how to leave. A user had to guess ctrl+c. Quitting and the
way to the rest of the keys are the two that have to be visible without asking.
"""


def fit(identity: data.Identity, stamp: str, width: int) -> str:
    """Return the widest status line that fits, shedding the least useful part first.

    The bar is one row, so anything too long would wrap and be clipped, taking
    the clock with it. The username, host and clock are what the bar exists for,
    so the site name goes first and the full name second, and only then is the
    line cut.

    The key hint is held to the right edge and outranks the host, the full name
    and the site name, since a reader who cannot see how to quit is worse off than
    one who cannot see which cluster they are on. It never outranks the username or
    the clock: an arrangement that has shed everything down to the clock alone is
    not one to spend fifteen columns of on a hint.
    """
    who = identity
    name = f" ({who.full_name})" if who.full_name else ""
    candidates = [
        f"{who.user}{name} @ {who.host}{GAP}{who.site_name}{GAP}{stamp}",
        f"{who.user}{name} @ {who.host}{GAP}{stamp}",
        f"{who.user} @ {who.host}{GAP}{stamp}",
        f"{who.user}{GAP}{stamp}",
        stamp,
    ]
    for line in candidates[:-1]:
        if len(line) + len(GAP) + len(KEYS) <= width:
            return line.ljust(width - len(KEYS)) + KEYS
    for line in candidates:
        if len(line) <= width:
            return line
    return candidates[-1][:width]


class StatusBar(Static):
    """Who you are, where you are, and the time, kept visible at all times.

    Markup is off because every field is outside our control: a full name comes
    from the GECOS field and the site name from a config file, so a square
    bracket in either would be parsed as a style tag and an unmatched closing
    tag would raise.
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
