"""The standing panel: fairshare, the GPU cap, and how recent work went."""

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from clustertool.tui import data, styles

TITLE = "Standing"

ACCOUNTS_SHOWN = 3
"""How many accounts the share line names before it counts the rest."""

LOW_SHARE = 0.5
CAP_WARN = 0.75
CAP_FULL = 1.0

NO_JOBS = "No jobs of yours ended in the window."

STATE_WORDS = {
    "COMPLETED": "done",
    "CANCELLED": "canceled",
    "FAILED": "failed",
    "TIMEOUT": "timeout",
    "OUT_OF_MEMORY": "oom",
    "PREEMPTED": "preempted",
    "OTHER": "other",
}
"""Plain words for the states, in the order the panel lists them."""


def share_style(score: str, color: bool = True) -> str:
    """Return the style for a fairshare score, empty when it is unremarkable.

    A score below a half means the account has used more than its share, so its jobs
    start behind others.
    """
    try:
        value = float(score)
    except ValueError:
        return "dim"
    return styles.resolve(styles.WARN, color) if value < LOW_SHARE else ""


def cap_style(used: int, cap: int | None, color: bool = True) -> str:
    """Return the style for the GPU line, which turns as the cap is approached."""
    if not cap:
        return "dim"
    fraction = used / cap
    if fraction >= CAP_FULL:
        return styles.resolve(styles.ALARM, color)
    return styles.resolve(styles.WARN, color) if fraction >= CAP_WARN else ""


def unread(note: str) -> str:
    """Say why a figure is missing, in words rather than a row marker."""
    return "still reading" if note == data.STILL_READING else note


def share_text(standing: data.Standing, width: int, color: bool = True) -> Text:
    """Render the fairshare line, naming the accounts with the most share first."""
    text = Text(no_wrap=True, overflow="crop")
    text.append("share    ", style="dim")
    if standing.share_note:
        text.append(f"unavailable: {unread(standing.share_note)}", style="dim")
        return _fit(text, width)
    if not standing.fairshare:
        text.append("no accounts reported", style="dim")
        return _fit(text, width)
    for account, score in standing.fairshare[:ACCOUNTS_SHOWN]:
        text.append(f"{account} ")
        text.append(f"{score}  ", style=share_style(score, color))
    extra = len(standing.fairshare) - ACCOUNTS_SHOWN
    if extra > 0:
        text.append(f"+{extra} more", style="dim")
    return _fit(text, width)


def gpu_text(standing: data.Standing, width: int, color: bool = True) -> Text:
    """Render the GPU line: the caller against their cap, their account against its.

    Both, since either can be what stops the next job starting. A count that could
    not be read says so rather than showing zero, which would read as room to spare.
    """
    text = Text(no_wrap=True, overflow="crop")
    text.append("gpus     ", style="dim")
    if standing.caps_note:
        text.append(f"unavailable: {unread(standing.caps_note)}", style="dim")
        return _fit(text, width)
    if standing.gpu_cap:
        text.append(
            f"{standing.gpus_used} of {standing.gpu_cap} yours",
            style=cap_style(standing.gpus_used, standing.gpu_cap, color),
        )
    elif standing.caps_known:
        text.append(f"{standing.gpus_used} running, no per-user cap", style="dim")
    else:
        text.append(f"{standing.gpus_used} running, cap unknown", style="dim")
    if standing.account and standing.account_cap:
        text.append("   ")
        text.append(f"{standing.account} ", style="dim")
        text.append(
            f"{standing.account_gpus} of {standing.account_cap}",
            style=cap_style(standing.account_gpus, standing.account_cap, color),
        )
        if standing.other_accounts:
            text.append(f" +{standing.other_accounts} more capped", style="dim")
    return _fit(text, width)


def states_text(standing: data.Standing, width: int) -> Text:
    """Render how the window's jobs ended, most common first."""
    text = Text(no_wrap=True, overflow="crop")
    text.append(f"last {standing.days}d  ", style="dim")
    if not standing.states:
        text.append(
            f"unavailable: {unread(standing.note)}" if standing.note else NO_JOBS, style="dim"
        )
        return _fit(text, width)
    parts = [
        f"{count} {STATE_WORDS.get(state, state.lower())}"
        for state, count in sorted(standing.states.items(), key=lambda item: -item[1])
    ]
    text.append(f"{standing.total} jobs: ")
    text.append(", ".join(parts))
    return _fit(text, width)


def efficiency_text(standing: data.Standing, width: int) -> Text:
    """Render the median utilization, naming how many jobs it was taken over.

    The count is part of the figure, since not every job carries metrics and a bare
    percentage would read as covering all of them.
    """
    text = Text(no_wrap=True, overflow="crop")
    text.append("median   ", style="dim")
    if not standing.measured:
        text.append("no job carried utilization data", style="dim")
        return _fit(text, width)
    text.append(f"cpu {standing.cpu}%  mem {standing.mem}%")
    if standing.gpu is not None:
        text.append(f"  gpu {standing.gpu}%")
        text.append(f" ({standing.gpu_jobs} gpu)", style="dim")
    text.append(f"  over {standing.measured} of {standing.total}", style="dim")
    return _fit(text, width)


IDLE_WARN = 50
IDLE_BAD = 75


def idle_style(unused: int, color: bool = True) -> str:
    """Return the style for the unused share, which is the point of showing it."""
    if unused >= IDLE_BAD:
        return styles.resolve(styles.ALARM, color)
    return styles.resolve(styles.WARN, color) if unused >= IDLE_WARN else ""


def unused_text(standing: data.Standing, width: int, color: bool = True) -> Text:
    """Render how much of the GPU time the caller held went unused.

    Weighted by how long each job held its GPUs, where the median above counts a
    one-minute job and a two-day one alike. The coverage is part of the figure, since
    not every GPU job records utilization.
    """
    text = Text(no_wrap=True, overflow="crop")
    text.append("unused   ", style="dim")
    hours = standing.hours
    text.append(
        f"{hours.unused}% of {hours.held:.0f} gpu-hours", style=idle_style(hours.unused, color)
    )
    text.append(f"  over {hours.covered} of {hours.gpu_jobs} gpu jobs", style="dim")
    return _fit(text, width)


def lines(standing: data.Standing, width: int, color: bool = True) -> list[Text]:
    """Render the whole panel, one line per fact.

    The median line is dropped when the window could not be read, and the unused line
    when no GPU job was measured, rather than showing a label with nothing after it.
    """
    out = [
        share_text(standing, width, color),
        gpu_text(standing, width, color),
        states_text(standing, width),
    ]
    if not standing.note:
        out.append(efficiency_text(standing, width))
        if standing.hours.unused is not None and standing.hours.covered:
            out.append(unused_text(standing, width, color))
    return out


TITLE_REASON_WORDS = 6
"""How many words of a failure the border title quotes.

The title is drawn in the border, so a longer reason is cut by the panel's width.
"""


def _stale_title(reason: str) -> Text:
    """Return the border title for a panel whose figures are old, naming the cause.

    A Text rather than a string: Textual parses a string title as content markup, and
    the reason here comes from a tool's stderr, where a bracket would either raise or
    style the border.
    """
    said = " ".join(reason.split()[:TITLE_REASON_WORDS])
    return Text(f"{TITLE} (stale: {said})" if said else f"{TITLE} (stale)")


def _fit(text: Text, width: int) -> Text:
    """Cut a line to the width it is drawn in, marking the cut.

    Marked because the tail here is usually a number, and a fairshare score cropped
    to 0. reads as a complete value.
    """
    room = max(width, 1)
    if len(text.plain) > room:
        text.truncate(max(room - 1, 0), overflow="crop")
        text.append("…")
    return text


class StandingPanel(VerticalScroll):
    """Fairshare, the GPU cap, and how the caller's recent jobs went.

    Keeps its last figures when a read fails, and keeps the share and the cap when
    only the accounting half is unavailable.
    """

    def __init__(self) -> None:
        super().__init__(id="standing", classes="panel")
        self._standing: data.Standing | None = None
        self._error = ""
        self._reading = False

    def compose(self):
        yield Static("", id="standing-body")

    def on_mount(self) -> None:
        self.border_title = TITLE
        self.can_focus = True
        self._paint()

    def begin_read(self) -> None:
        """Say that a read is under way, keeping the border and the last figures."""
        self._reading = True
        self.border_title = f"{TITLE} (reading)"
        self._paint()

    def end_read(self) -> None:
        """Clear the reading mark if it is still set, whatever ended the read."""
        if self._reading:
            self._reading = False
            self.border_title = _stale_title(self._error) if self._error else TITLE
            self._paint()

    def show(self, standing: data.Standing) -> None:
        """Replace the panel with these figures."""
        self._standing, self._error, self._reading = standing, "", False
        self.border_title = TITLE
        self._paint()

    def fail(self, reason: str) -> None:
        """Mark the panel stale, naming the cause and keeping whatever it held.

        The cause goes on the border title rather than a line of the body, which has
        exactly as many rows as the panel has facts.
        """
        self._error, self._reading = reason, False
        self.border_title = _stale_title(reason)
        self._paint()

    def on_resize(self, _event) -> None:
        self._paint()

    @property
    def ready(self) -> bool:
        """Whether this panel's own widgets exist yet.

        A query can land before Textual has mounted them, and looking one up then
        raises inside the worker whose job is to report failures.
        """
        return bool(self.query("#standing-body"))

    def _paint(self) -> None:
        """Draw the panel, using every row it has for figures.

        Neither the reading mark nor the stale reason takes a line while there are
        figures to show, since the border title carries both. With no figures yet the
        body says what is happening instead.
        """
        if not self.ready:
            return
        body = self.query_one("#standing-body", Static)
        width = max(self.content_size.width - 1, 12)
        blocks: list[Text] = []
        if self._standing is None:
            said = f"stale: {self._error}" if self._error else "reading your standing"
            blocks.append(_fit(Text(said, style="dim"), width))
        else:
            blocks.extend(lines(self._standing, width, not self.app.no_color))
        body.update(Text("\n", no_wrap=True, overflow="crop").join(blocks))
