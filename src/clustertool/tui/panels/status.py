"""The status bar along the bottom of the dashboard."""

import datetime

from textual.reactive import reactive
from textual.widgets import Static

from clustertool.tui import data

CLOCK_FORMAT = "%a %Y-%m-%d %H:%M"


class StatusBar(Static):
    """Who you are, where you are, and the time, kept visible at all times.

    The clock reads through an injected callable so a test can pin it and a
    snapshot stays stable.
    """

    now = reactive(datetime.datetime.now)

    def __init__(self, identity: data.Identity, clock=datetime.datetime.now) -> None:
        super().__init__(id="status")
        self._identity = identity
        self._clock = clock

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)

    def render(self) -> str:
        who = self._identity
        name = f" ({who.full_name})" if who.full_name else ""
        left = f"{who.user}{name} @ {who.host}"
        stamp = self._clock().strftime(CLOCK_FORMAT)
        return f"{left}   {who.site_name}   {stamp}"
