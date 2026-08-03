"""The me dashboard application."""

import asyncio
import datetime
import textwrap
import threading
from collections.abc import Callable

from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static

from clustertool.process import CommandError
from clustertool.tui import actions, data
from clustertool.tui.panels.jobs import JobsPanel
from clustertool.tui.panels.standing import StandingPanel
from clustertool.tui.panels.status import StatusBar
from clustertool.tui.panels.storage import StoragePanel

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
  r            refresh the focused panel
  R            refresh every panel
  ?            this help
  Q            quit

On the selected job, each asking first

  c            cancel it
  h            hold it
  H            release it
  ctrl+r       requeue it, discarding the work so far

Read-only, on the selected job

  l            the tail of its output
  f            follow its output, escape or f to stop
  w            why it is not running
  s            how well it used what it asked for
  y            copy its id
"""


def _reason(exc: BaseException) -> str:
    """Describe a failure for the panel, naming the class only when it adds anything.

    A CommandError already reads as a sentence about the cluster. Anything else is
    unexpected, and its type is most of what there is to say about it.
    """
    if isinstance(exc, CommandError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


async def detached(call: Callable):
    """Run a blocking call on a daemon thread and await its result.

    Not asyncio.to_thread, whose executor threads are joined before the
    interpreter exits: a query still running there held quitting for as long as it
    took, which for a hanging filesystem tool was the whole of its deadline. A
    daemon thread is abandoned instead, so Q returns at once whatever is in
    flight.
    """
    loop = asyncio.get_running_loop()
    done = loop.create_future()

    def deliver(setter, value) -> None:
        if not done.done():
            setter(value)

    def post(setter, value) -> None:
        try:
            loop.call_soon_threadsafe(deliver, setter, value)
        except RuntimeError:
            return

    def run() -> None:
        try:
            result = call()
        except BaseException as exc:
            post(done.set_exception, exc)
        else:
            post(done.set_result, result)

    threading.Thread(target=run, daemon=True, name="clustertool-query").start()
    return await done


BANNER_ROWS = 2
"""How many rows the banner may wrap to, matching its max-height in the stylesheet."""


def _shorten(said: str, width: int) -> str:
    """Cut a banner line to the rows it has, marking the cut where it lands.

    A refusal runs to a couple of hundred characters and the banner has two rows,
    so the end of the reason was simply gone with nothing to say it had been. The
    cut is found by wrapping rather than by counting characters: two rows of N
    columns do not hold 2N characters of prose, so a character budget put the
    ellipsis on a third row that the height then clipped, which is to say it marked
    the cut somewhere nobody could see.
    """
    if width < 4:
        return said[:width]
    rows = textwrap.wrap(said, width) or [""]
    if len(rows) <= BANNER_ROWS:
        return said
    kept = rows[:BANNER_ROWS]
    kept[-1] = kept[-1][: max(width - 1, 1)].rstrip() + "…"
    return "\n".join(kept)


def _settle(panel, info=None, reason="") -> None:
    """Show the result, or the failure when there is one."""
    if reason:
        panel.fail(reason)
    else:
        panel.show(info)


class ConfirmScreen(ModalScreen[bool]):
    """Ask before changing a job, defaulting to No.

    No is focused on open and escape dismisses, so the safe answer is both the
    default and the one a stray keypress gives. The job is named in full, since a
    confirmation that does not identify its target only trains people to accept it.
    """

    BINDINGS = [("escape", "refuse", "no")]

    def __init__(self, action: actions.Action, subject: str) -> None:
        super().__init__()
        self._action = action
        self._subject = subject

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm"), Vertical(id="confirm-body"):
            yield Static(self._action.question, id="confirm-question", markup=False)
            yield Static(self._subject, id="confirm-subject", markup=False)
            if self._action.caution:
                yield Static(self._action.caution, id="confirm-caution", markup=False)
            with Horizontal(id="confirm-buttons"):
                yield Button("No", variant="primary", id="confirm-no")
                yield Button(f"Yes, {self._action.name}", variant="error", id="confirm-yes")

    def on_mount(self) -> None:
        self.query_one("#confirm-no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def action_refuse(self) -> None:
        self.dismiss(False)


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
        *((action.key, f"act('{action.name}')", action.name) for action in actions.MUTATING),
        ("l", "look('log')", "log"),
        ("f", "follow", "follow"),
        ("w", "look('why')", "why"),
        ("s", "look('scope')", "scope"),
        ("y", "copy_id", "copy id"),
        ("Q", "quit", "quit"),
        ("ctrl+c", "quit", "quit"),
        ("question_mark", "help", "help"),
        ("r", "refresh", "refresh"),
        ("R", "refresh_all", "refresh all"),
        ("escape", "stop_following", "stop following"),
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
        self._loading_storage = False
        self._loading_standing = False
        self._following: str | None = None
        self._follow_timer = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            yield JobsPanel()
            yield StoragePanel()
        yield StandingPanel()
        yield Static("", id="banner", markup=False)
        yield StatusBar(self._identity, clock=self._clock)

    def on_mount(self) -> None:
        self.query_one("#jobs-table", DataTable).focus()
        if self._interval > 0:
            self.load_jobs()
            self.load_storage()
            self.load_standing()
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
            rows = await detached(lambda: data.jobs(self._identity.user))
            self._on(JobsPanel, lambda panel: panel.show(rows))
        except Exception as exc:
            reason = _reason(exc)
            self._on(JobsPanel, lambda panel: panel.fail(reason))
        finally:
            self._loading = False

    def _on(self, kind: type, action: Callable) -> None:
        """Run action on a panel if it is still mounted, and drop it if not.

        A worker outlives the screen when the app is shutting down with a query in
        flight. The lookup then raises, and doing that inside the handler that
        reports a failure replaces the failure with a WorkerFailed and a traceback
        over the terminal, which is the thing the handler exists to prevent.
        """
        try:
            panel = self.query_one(kind)
        except NoMatches:
            return
        action(panel)

    def on_resize(self, event: events.Resize) -> None:
        """Drop the side column when two panels no longer fit across the terminal.

        Both panels hold a width floor, and below their sum the pair is drawn off
        the right edge: the second panel loses its right border and whatever it
        holds is simply not on screen. One panel that fits beats two that do not.
        """
        self.query_one("#storage").display = event.size.width >= SIDE_BY_SIDE

    @work(group="storage")
    async def load_storage(self) -> None:
        """Read the quotas off the filesystems without blocking the interface.

        Not on the timer: quotas move slowly, the fan-out is a second warm and six
        cold, and every viewer of this dashboard would be putting that on a shared
        quota service every few seconds for a figure that had not changed.
        """
        if self._loading_storage:
            return
        self._loading_storage = True
        self._on(StoragePanel, lambda panel: panel.begin_read())
        try:
            info = await detached(lambda: data.storage_info(self._identity.user))
            self._on(StoragePanel, lambda panel: _settle(panel, info=info))
        except Exception as exc:
            reason = _reason(exc)
            self._on(StoragePanel, lambda panel: _settle(panel, reason=reason))
        finally:
            self._loading_storage = False
            self._on(StoragePanel, lambda panel: panel.end_read())

    @work(group="standing")
    async def load_standing(self) -> None:
        """Read fairshare, the cap and the recent window without blocking the interface.

        Not on the timer: a fairshare score moves on the decay half-life, which is
        three days here, and the window is a week wide.
        """
        if self._loading_standing:
            return
        self._loading_standing = True
        self._on(StandingPanel, lambda panel: panel.begin_read())
        try:
            info = await detached(lambda: data.standing(self._identity.user))
            self._on(StandingPanel, lambda panel: _settle(panel, info=info))
        except Exception as exc:
            reason = _reason(exc)
            self._on(StandingPanel, lambda panel: _settle(panel, reason=reason))
        finally:
            self._loading_standing = False
            self._on(StandingPanel, lambda panel: panel.end_read())

    def action_refresh(self) -> None:
        """Read the focused panel again now, rather than waiting for the timer."""
        focused = self._focused_panel()
        if focused is StoragePanel:
            self.load_storage()
            return
        if focused is StandingPanel:
            self.load_standing()
            return
        self.load_jobs()

    def _focused_panel(self) -> type | None:
        """Return the panel class holding focus, which decides what r refreshes."""
        focused = self.focused
        if focused is None:
            return None
        for widget in focused.ancestors_with_self:
            if isinstance(widget, StoragePanel | JobsPanel | StandingPanel):
                return type(widget)
        return None

    def action_refresh_all(self) -> None:
        """Read every panel again, whichever one has focus.

        A hidden side column is skipped: on a narrow terminal it is not on screen,
        and its fan-out is forty lookups nobody would see the result of.
        """
        self.load_jobs()
        self.load_standing()
        if self.query_one("#storage").display:
            self.load_storage()

    def action_act(self, name: str) -> None:
        """Ask before doing something to the selected job, then do it.

        Nothing happens without an answer, and the answer is not remembered: a
        confirmation that only appears once is a confirmation for the first job.
        """
        panel = self.query_one(JobsPanel)
        row = panel.selected
        if row is None:
            self.announce("no job is selected")
            return
        action = next(item for item in actions.MUTATING if item.name == name)
        self.push_screen(
            ConfirmScreen(action, actions.describe(action, row)),
            lambda yes: self.do_act(name, row.jobid) if yes else self.announce(f"{name} canceled"),
        )

    @work(group="act")
    async def do_act(self, name: str, jobid: str) -> None:
        """Run a confirmed action off the interface thread, then reread the jobs."""
        try:
            said = await detached(lambda: actions.run(name, jobid))
        except Exception as exc:
            self.announce(_reason(exc))
            return
        self.announce(said)
        self.load_jobs()

    def announce(self, said: str) -> None:
        """Put a line on the banner, which is where an action reports itself.

        Control characters are dropped: what a tool wrote to stderr ends up here,
        and an escape byte in it would be a command to the terminal rather than
        text on the banner.
        """
        try:
            banner = self.query_one("#banner", Static)
            width = max(banner.content_size.width, 1)
            banner.update(_shorten(actions.printable(said), width))
        except NoMatches:
            return

    def action_look(self, what: str) -> None:
        """Read something about the selected job and show it under the detail."""
        row = self.query_one(JobsPanel).selected
        if row is None:
            self.announce("no job is selected")
            return
        self.fetch_look(what, row.jobid)

    @work(group="look")
    async def fetch_look(self, what: str, jobid: str) -> None:
        """Do the read off the interface thread, since both shell out."""
        reader = {"log": actions.log_tail, "why": actions.why, "scope": actions.scope}[what]
        try:
            said = await detached(lambda: reader(jobid))
        except Exception as exc:
            self.announce(_reason(exc))
            return
        self._on(JobsPanel, lambda panel: panel.show_text(said, jobid))

    def action_follow(self) -> None:
        """Keep rereading the selected job's log until escape stops it.

        A second press stops it too, so the key that starts it can also end it
        without the reader having to remember which one does.
        """
        if self._following is not None:
            self.stop_following("stopped following")
            return
        row = self.query_one(JobsPanel).selected
        if row is None:
            self.announce("no job is selected")
            return
        self._following = row.jobid
        self.announce(f"following {row.jobid}, escape to stop")
        self.fetch_look("log", row.jobid)
        self._follow_timer = self.set_interval(
            actions.FOLLOW_INTERVAL_S, lambda: self.fetch_look("log", row.jobid)
        )

    def action_stop_following(self) -> None:
        """Stop following, and say nothing if nothing was being followed."""
        if self._following is not None:
            self.stop_following("stopped following")

    def stop_following(self, said: str) -> None:
        """Cancel the follow timer and report it once."""
        if self._follow_timer is not None:
            self._follow_timer.stop()
            self._follow_timer = None
        self._following = None
        self.announce(said)

    def action_copy_id(self) -> None:
        """Put the selected job id on the clipboard, so it can be pasted elsewhere."""
        row = self.query_one(JobsPanel).selected
        if row is None:
            self.announce("no job is selected")
            return
        self.copy_to_clipboard(row.jobid)
        self.announce(f"copied {row.jobid}")

    def action_help(self) -> None:
        """Open the key reference, which is the only discovery route for the bindings."""
        self.push_screen(HelpScreen())


def run(identity: data.Identity | None = None) -> None:
    """Start the dashboard, returning when the user quits."""
    MeApp(identity=identity).run()
