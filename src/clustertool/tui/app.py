"""The me dashboard application."""

import asyncio
import datetime
import textwrap
import threading
from collections.abc import Callable

from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, OptionList, Static
from textual.widgets.option_list import Option

from clustertool.process import CommandError
from clustertool.tui import actions, data
from clustertool.tui.panels.jobs import JobsPanel, elide, wrapped
from clustertool.tui.panels.standing import StandingPanel
from clustertool.tui.panels.status import StatusBar
from clustertool.tui.panels.storage import StoragePanel

SIDE_BY_SIDE = 80
"""Narrowest terminal that still holds the jobs panel and the side column together.

Below it the side column goes underneath rather than past the right edge. The jobs
panel has no width floor of its own, since a floor cannot make a panel fit a
narrower terminal and would only push it off the edge.

80 rather than the sum of the two floors, which is 48: bringing the side column back
costs the table that whole width at once, and 80 is the first width where the table
keeps every column it had without it.
"""

THEMES = {"dark": "textual-dark", "light": "textual-light", "ansi": "ansi-dark"}
"""Short names for the themes worth naming, mapped to Textual's own.

Any other Textual theme name is passed through. The app paints its own background,
so the theme rather than the terminal decides whether the screen is light; the ansi
themes instead use the terminal's own sixteen colors.
"""

KEY_COLUMN = 13
"""Where a description starts in the help overlay, which lists shift+tab."""

MENU_BOX = 4
"""Rows the menu's border and padding take."""

MENU_SUBJECT_ROWS = 2
"""Rows of text the line naming the job may wrap onto."""

MENU_SUBJECT = MENU_SUBJECT_ROWS + 1
"""Rows that line costs in all, the padding under it included.

It is also the line's max-height in app.tcss, since a widget's padding is inside its
height there.
"""

MENU_WIDTH = 62
"""The menu's width in app.tcss, which it is never wider than."""

MENU_SIDES = 6
"""Columns the menu's border and padding take."""

MENU_SUBJECT_FLOOR = 16
"""Narrowest the line naming the job is wrapped to, however narrow the terminal."""

MENU_CHROME = MENU_BOX + MENU_SUBJECT
"""Rows the menu spends on anything but an action."""

MENU_KEY_COLUMN = 8
"""Where a description starts in the menu, whose longest key is ctrl+r.

Narrower than the help overlay's column, which has to fit shift+tab.
"""

MENU_OPENS_ON = [action.name for action in actions.MENU].index("cancel")
"""Which entry the menu highlights, found by name so reordering cannot move it."""


def _keys(offered: tuple[actions.Action, ...]) -> str:
    """List actions as key and description, one per line."""
    return "\n".join(f"  {action.key:<{KEY_COLUMN}}{action.label}" for action in offered)


HELP = f"""\
Keys

  {"up down":<{KEY_COLUMN}}move between jobs
  {"enter":<{KEY_COLUMN}}menu for the selected job
  {"tab":<{KEY_COLUMN}}next panel
  {"shift+tab":<{KEY_COLUMN}}previous panel
  {"r":<{KEY_COLUMN}}refresh the focused panel
  {"R":<{KEY_COLUMN}}refresh every panel
  {"escape":<{KEY_COLUMN}}stop following
  {"?":<{KEY_COLUMN}}this help
  {"Q":<{KEY_COLUMN}}quit

On the selected job, each asking first

{_keys(actions.MUTATING)}

Read-only, on the selected job

{_keys(actions.READING)}
"""
"""The key reference, built from the same table the menu and the bindings read."""


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

    Not asyncio.to_thread, whose executor threads are joined before the interpreter
    exits, so a hanging query would hold up quitting. A daemon thread is abandoned
    instead, and Q returns at once.
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

BANNER_PADDING = 2
"""Columns the banner's own padding takes, matching its rule in the stylesheet.

The width is measured from the screen rather than the widget, which reports nothing
while it is hidden.
"""


def _shorten(said: str, width: int) -> str:
    """Cut a banner line to the rows it has, marking the cut where it lands.

    A refusal can run to a couple of hundred characters against the banner's two
    rows. The cut is found by wrapping rather than by counting characters, since two
    rows of N columns do not hold 2N characters of prose and the mark would land on a
    row the height then clips.
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

    No is focused on open and escape dismisses, so the safe answer is both the default
    and what a stray keypress gives. The job is named in full.
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


class ActionMenu(ModalScreen[str | None]):
    """Everything the keys do to one job, offered as a list.

    Opens on cancel, since that is what most callers come here for, and every
    mutating choice still asks before it runs. Each row shows its key, so the menu
    teaches the shortcut rather than replacing it.
    """

    BINDINGS = [("escape", "close", "close")]

    def __init__(self, subject: str) -> None:
        super().__init__()
        self._subject = subject
        self._answered = False

    def compose(self) -> ComposeResult:
        with Vertical(id="menu"), Vertical(id="menu-body"):
            yield Static(self._subject, id="menu-subject", markup=False)
            yield OptionList(
                *(
                    Option(f"{action.key:<{MENU_KEY_COLUMN}}{action.label}", id=action.name)
                    for action in actions.MENU
                ),
                id="menu-options",
                markup=False,
            )

    def on_mount(self) -> None:
        options = self.query_one("#menu-options", OptionList)
        options.focus()
        options.highlighted = MENU_OPENS_ON
        self._fit()

    def on_resize(self, _event) -> None:
        self._fit()

    def _fit(self) -> None:
        """Set a definite height, which is what lets the list scroll rather than clip.

        Never taller than the screen, so the box is not drawn past an edge, and the
        line naming the job gives way when the box is too short to hold both it and an
        entry to choose.
        """
        body = self.query_one("#menu-body")
        wanted = len(actions.MENU) + MENU_CHROME
        height = min(wanted, max(self.size.height - 2, 1))
        body.styles.height = height
        subject = self.query_one("#menu-subject", Static)
        subject.display = height - MENU_BOX > MENU_SUBJECT
        subject.update(self._named())

    def _named(self) -> str:
        """Return the line naming the job, wrapped to the rows it has and marked if cut.

        Wrapped here rather than by the renderer, which would silently clip whatever did
        not fit the two rows the line is allowed. The width comes from the screen, since
        the widget does not know its own until after this has run.
        """
        room = min(MENU_WIDTH, max(self.size.width * 9 // 10, 1))
        width = max(room - MENU_SIDES, MENU_SUBJECT_FLOOR)
        rows = wrapped(self._subject, width)
        if len(rows) > MENU_SUBJECT_ROWS:
            rows = rows[:MENU_SUBJECT_ROWS]
            rows[-1] = elide(rows[-1] + "…", width)
        return "\n".join(rows)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Answer with the chosen action, once.

        Two selection events can arrive together when input outruns the message pump,
        and a second dismiss pops a screen this one no longer owns.
        """
        if self._answered:
            return
        self._answered = True
        self.dismiss(event.option.id)

    def action_close(self) -> None:
        if self._answered:
            return
        self._answered = True
        self.dismiss(None)


class HelpScreen(ModalScreen):
    """The key reference, shown over the dashboard.

    It scrolls, since the list is longer than a terminal of twenty-four rows can hold
    and a key nobody can see is the thing this screen exists to prevent.
    """

    BINDINGS = [("escape,question_mark,Q", "dismiss", "close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="help"), VerticalScroll(id="help-body"):
            yield Static(HELP, id="help-text")

    def on_mount(self) -> None:
        self.query_one("#help-body", VerticalScroll).focus()


class MeApp(App):
    """One screen showing where the caller stands on the cluster."""

    TITLE = "clustertool me"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        *((action.key, f"choose('{action.name}')", action.name) for action in actions.MENU),
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
        days: int = data.STANDING_DAYS,
        theme: str | None = None,
    ) -> None:
        super().__init__()
        self._identity = identity or data.identity()
        self._clock = clock
        self._interval = interval
        self._days = days
        self._theme = theme
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
        banner = Static("", id="banner", markup=False)
        banner.display = False
        yield banner
        yield StatusBar(self._identity, clock=self._clock)

    def on_mount(self) -> None:
        self.apply_theme()
        self.query_one("#jobs-table", DataTable).focus()
        if self._interval > 0:
            self.load_jobs()
            self.load_storage()
            self.load_standing()
            self.set_interval(self._interval, self.load_jobs)

    def apply_theme(self) -> None:
        """Switch to the theme that was asked for, saying so if there is no such thing.

        Nothing is set when none was named, so TEXTUAL_THEME keeps working. An unknown
        name is reported on the banner rather than raised.
        """
        if not self._theme:
            return
        wanted = THEMES.get(self._theme, self._theme)
        if wanted not in self.available_themes:
            self.announce(f"no theme called {self._theme}; showing {self.theme}")
            return
        self.theme = wanted

    @work(group="jobs")
    async def load_jobs(self) -> None:
        """Read the jobs off the scheduler without blocking the interface.

        Guarded by a flag rather than an exclusive worker, which would cancel only the
        awaiting coroutine and leave the squeue subprocess running, so a held-down
        refresh key would still reach the controller once per keypress. Every failure
        lands on the panel rather than tearing down the screen.
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

        A worker outlives the screen when the app is quitting with a query in flight,
        and the lookup then raises inside the handler meant to report the failure.
        """
        try:
            panel = self.query_one(kind)
        except NoMatches:
            return
        action(panel)

    def on_resize(self, event: events.Resize) -> None:
        """Stack the panels when they no longer fit across the terminal.

        Side by side below their combined width floor, the second panel is drawn past
        the right edge. Stacking keeps it on screen, so a narrow terminal loses the
        arrangement rather than the quotas.
        """
        self.query_one("#body").set_class(event.size.width < SIDE_BY_SIDE, "stacked")

    @work(group="storage")
    async def load_storage(self) -> None:
        """Read the quotas off the filesystems without blocking the interface.

        Not on the timer: quotas move slowly and the fan-out is expensive on a shared
        service. Refreshed on r or R instead.
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
            info = await detached(lambda: data.standing(self._identity.user, days=self._days))
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

        Every panel, since a narrow terminal stacks the side column rather than hiding
        it, so there is none whose result nobody would see.
        """
        self.load_jobs()
        self.load_standing()
        self.load_storage()

    def action_choose(self, name: str) -> None:
        """Do an action to the selected job, which is what each of its keys does.

        Follow is the one that toggles: pressing its key again stops it, so the key
        that starts a follow can also end it.
        """
        if name == "follow" and self._following is not None:
            self.stop_following("stopped following")
            return
        row = self._chosen()
        if row is not None:
            self.chose(name, row)

    def _chosen(self) -> data.JobRow | None:
        """Return the selected row, or say there is none to act on."""
        row = self.query_one(JobsPanel).selected
        if row is None:
            self.announce("no job is selected")
        return row

    def confirm_act(self, name: str, row: data.JobRow) -> None:
        """Ask about this job, then act on it.

        Nothing happens without an answer, and the answer is not remembered: a
        confirmation that only appears once is a confirmation for the first job. The
        job is captured here rather than read again when the answer lands, since the
        table refreshes on its own while the question is up.
        """
        action = actions.BY_NAME[name]
        self.push_screen(
            ConfirmScreen(action, actions.describe(row)),
            lambda yes: self.do_act(name, row.jobid) if yes else self.announce(f"{name} canceled"),
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open the menu on the job enter was pressed on, which is what enter does.

        The job comes from the event rather than from the cursor, which the refresh
        timer can move between the keypress and this handler. Ignored while a modal is
        up, since a burst of keypresses would otherwise stack one menu per press.
        """
        if self.screen is not self.screen_stack[0]:
            return
        row = self._row_of(event)
        if row is None:
            return
        self.push_screen(
            ActionMenu(actions.describe(row)),
            lambda name: self.chose(name, row) if name else None,
        )

    def _row_of(self, event: DataTable.RowSelected) -> data.JobRow | None:
        """Return the job the event names, or say there is none."""
        panel = self.query_one(JobsPanel)
        row = next((item for item in panel.rows if item.jobid == event.row_key.value), None)
        if row is None:
            self.announce("that job is no longer in the table")
        return row

    def chose(self, name: str, row: data.JobRow) -> None:
        """Do what was chosen, on the job it was chosen for."""
        if actions.BY_NAME[name].mutating:
            self.confirm_act(name, row)
            return
        reader = {
            "copy": self.copy_id,
            "follow": self.follow,
            "log": lambda job: self.fetch_look("log", job.jobid),
            "why": lambda job: self.fetch_look("why", job.jobid),
            "scope": lambda job: self.fetch_look("scope", job.jobid),
        }[name]
        reader(row)

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

        The banner takes no room until it has something to say, since on a short
        terminal its row is one the panels need. Control characters are dropped,
        because a tool's stderr ends up here and an escape byte in it would be a
        command to the terminal.
        """
        try:
            banner = self.query_one("#banner", Static)
            banner.display = bool(said)
            width = max(self.size.width - BANNER_PADDING, 1)
            banner.update(_shorten(actions.printable(said), width))
        except NoMatches:
            return

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

    def follow(self, row: data.JobRow) -> None:
        """Keep rereading this job's log until escape stops it.

        Any follow already running is stopped first. Two timers cannot be stopped by
        one escape, and the one left behind goes on reading a file nobody asked about.
        """
        if self._follow_timer is not None:
            self._follow_timer.stop()
            self._follow_timer = None
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

    def copy_id(self, row: data.JobRow) -> None:
        """Put this job's id on the clipboard."""
        self.copy_to_clipboard(row.jobid)
        self.announce(f"copied {row.jobid}")

    def action_help(self) -> None:
        """Open the key reference, which is the only discovery route for the bindings."""
        self.push_screen(HelpScreen())


def run(
    identity: data.Identity | None = None,
    interval: float = 5.0,
    days: int = data.STANDING_DAYS,
    theme: str | None = None,
) -> None:
    """Start the dashboard, returning when the user quits."""
    MeApp(identity=identity, interval=interval, days=days, theme=theme).run()
