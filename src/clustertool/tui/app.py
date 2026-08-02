"""The me dashboard application."""

import asyncio
import datetime
from collections.abc import Callable

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from clustertool.process import CommandError
from clustertool.tui import data
from clustertool.tui.panels.jobs import JobsPanel
from clustertool.tui.panels.status import StatusBar

HELP = """\
Keys

  up down      move between jobs
  tab          next panel
  shift+tab    previous panel
  r            refresh the jobs now
  ?            this help
  Q            quit
"""


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

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            yield JobsPanel()
            yield Static("", id="storage", classes="panel")
        yield Static("", id="standing", classes="panel")
        yield StatusBar(self._identity, clock=self._clock)

    def on_mount(self) -> None:
        for widget_id, title in (
            ("#jobs", "Jobs"),
            ("#storage", "Storage"),
            ("#standing", "Standing"),
        ):
            panel = self.query_one(widget_id)
            panel.border_title = title
            if widget_id != "#jobs":
                panel.can_focus = True
        self.query_one("#jobs-table", DataTable).focus()
        if self._interval > 0:
            self.load_jobs()
            self.set_interval(self._interval, self.load_jobs)

    @work(exclusive=True, group="jobs")
    async def load_jobs(self) -> None:
        """Read the jobs off the scheduler without blocking the interface.

        Exclusive so a held-down refresh key cannot stack queries on a busy
        controller.
        """
        panel = self.query_one(JobsPanel)
        try:
            rows = await asyncio.to_thread(data.jobs, self._identity.user)
        except CommandError as exc:
            panel.fail(str(exc))
            return
        panel.show(rows)

    def action_refresh(self) -> None:
        """Read the jobs again now, rather than waiting for the timer."""
        self.load_jobs()

    def action_help(self) -> None:
        """Open the key reference, which is the only discovery route for the bindings."""
        self.push_screen(HelpScreen())


def run(identity: data.Identity | None = None) -> None:
    """Start the dashboard, returning when the user quits."""
    MeApp(identity=identity).run()
