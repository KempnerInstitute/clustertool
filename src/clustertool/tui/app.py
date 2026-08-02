"""The me dashboard application."""

import asyncio
import datetime
from collections.abc import Callable

from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from clustertool.process import CommandError
from clustertool.tui import data
from clustertool.tui.panels.jobs import JobsPanel
from clustertool.tui.panels.status import StatusBar

SIDE_BY_SIDE = 80
"""Narrowest terminal that still holds the jobs panel and the side column together.

Below it the side column is hidden rather than drawn past the right edge. The
jobs panel carries no floor of its own: a floor cannot make a panel fit a
terminal narrower than itself, it only pushes the panel off the right edge, which
is the very thing this constant exists to prevent.

80 rather than the sum of the floors, which was 48: bringing the side column back
costs the jobs table the side column's whole width at once, and at 48 that took
the table from five columns to two, so widening the terminal by one lost three
headings. 80 is the first width where the table keeps every column it had at 79,
measured across 30 to 130 columns.
"""

HELP = """\
Keys

  up down      move between jobs
  tab          next panel
  shift+tab    previous panel
  r            refresh the jobs now
  ?            this help
  Q            quit
"""


def _reason(exc: BaseException) -> str:
    """Describe a failure for the panel, naming the class only when it adds anything.

    A CommandError already reads as a sentence about the cluster. Anything else is
    unexpected, and its type is most of what there is to say about it.
    """
    if isinstance(exc, CommandError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


class HelpScreen(ModalScreen):
    """The key reference, shown over the dashboard."""

    BINDINGS = [("escape,question_mark,Q", "dismiss", "close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="help"):
            yield Static(HELP, id="help-body")


class MeApp(App):
    """One screen showing where the caller stands on the cluster."""

    TITLE = "clustertool me"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("Q", "quit", "quit"),
        ("ctrl+c", "quit", "quit"),
        ("question_mark", "help", "help"),
        ("r", "refresh", "refresh"),
        ("tab", "focus_next", "next panel"),
        ("shift+tab", "focus_previous", "previous panel"),
    ]

    def __init__(
        self,
        identity: data.Identity | None = None,
        clock: Callable[[], datetime.datetime] = datetime.datetime.now,
        interval: float = 5.0,
    ) -> None:
        super().__init__()
        self._identity = identity or data.identity()
        self._clock = clock
        self._interval = interval
        self._loading = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            yield JobsPanel()
            yield Static("", id="storage", classes="panel")
        yield Static("", id="standing", classes="panel")
        yield StatusBar(self._identity, clock=self._clock)

    def on_mount(self) -> None:
        for widget_id, title in (("#storage", "Storage"), ("#standing", "Standing")):
            panel = self.query_one(widget_id)
            panel.border_title = title
            panel.can_focus = True
        self.query_one("#jobs-table", DataTable).focus()
        if self._interval > 0:
            self.load_jobs()
            self.set_interval(self._interval, self.load_jobs)

    @work(group="jobs")
    async def load_jobs(self) -> None:
        """Read the jobs off the scheduler without blocking the interface.

        A flag rather than an exclusive worker, which cancels only the coroutine
        that awaits the thread: the squeue subprocess runs to completion whatever
        happens to its awaiter, so a held-down refresh key would still put one
        query per keypress on the controller. Every failure lands on the panel,
        including the ones that are this code's fault, because a dashboard that
        tears down its own screen is worse than one showing a stale table.
        """
        if self._loading:
            return
        self._loading = True
        try:
            rows = await asyncio.to_thread(data.jobs, self._identity.user)
            self.query_one(JobsPanel).show(rows)
        except Exception as exc:
            self.query_one(JobsPanel).fail(_reason(exc))
        finally:
            self._loading = False

    def on_resize(self, event: events.Resize) -> None:
        """Drop the side column when two panels no longer fit across the terminal.

        Both panels hold a width floor, and below their sum the pair is drawn off
        the right edge: the second panel loses its right border and whatever it
        holds is simply not on screen. One panel that fits beats two that do not.
        """
        self.query_one("#storage").display = event.size.width >= SIDE_BY_SIDE

    def action_refresh(self) -> None:
        """Read the jobs again now, rather than waiting for the timer."""
        self.load_jobs()

    def action_help(self) -> None:
        """Open the key reference, which is the only discovery route for the bindings."""
        self.push_screen(HelpScreen())


def run(identity: data.Identity | None = None) -> None:
    """Start the dashboard, returning when the user quits."""
    MeApp(identity=identity).run()
