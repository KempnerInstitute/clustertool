"""The standing panel: fairshare, the GPU cap, and how recent work went."""

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from clustertool.tui import data

TITLE = "Standing"

ACCOUNTS_SHOWN = 3
"""How many accounts the share line names before it counts the rest.

A user can belong to twenty, and the panel has one line for this.
"""

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


def share_style(score: str) -> str:
    """Return the style for a fairshare score, empty when it is unremarkable.

    A score below a half means the account has used more than its share and its
    jobs will start behind others, which is the one thing worth a color here.
    """
    try:
        value = float(score)
    except ValueError:
        return "dim"
    return "yellow" if value < LOW_SHARE else ""


def cap_style(used: int, cap: int | None) -> str:
    """Return the style for the GPU line, which turns as the cap is approached."""
    if not cap:
        return "dim"
    fraction = used / cap
    if fraction >= CAP_FULL:
        return "bold red"
    return "yellow" if fraction >= CAP_WARN else ""


def unread(note: str) -> str:
    """Say why a figure is missing, in words rather than a row marker."""
    return "still reading" if note == data.STILL_READING else note


def share_text(standing: data.Standing, width: int) -> Text:
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
        text.append(f"{score}  ", style=share_style(score))
    extra = len(standing.fairshare) - ACCOUNTS_SHOWN
    if extra > 0:
        text.append(f"+{extra} more", style="dim")
    return _fit(text, width)


def gpu_text(standing: data.Standing, width: int) -> Text:
    """Render the GPU line: the caller against their cap, their account against its.

    Both, because either can be what stops the next job starting, and they are
    different limits. Reading a user's own usage against the account cap, which is
    six times larger here, said they had room they did not have.

    A count that could not be read says so rather than showing nought against the
    cap, which reads as all the room being free when a query simply did not return.
    """
    text = Text(no_wrap=True, overflow="crop")
    text.append("gpus     ", style="dim")
    if standing.caps_note:
        text.append(f"unavailable: {unread(standing.caps_note)}", style="dim")
        return _fit(text, width)
    if standing.gpu_cap:
        text.append(
            f"{standing.gpus_used} of {standing.gpu_cap} yours",
            style=cap_style(standing.gpus_used, standing.gpu_cap),
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
            style=cap_style(standing.account_gpus, standing.account_cap),
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

    The count is part of the figure: fewer than half of this caller's jobs carry
    metrics at all, and a bare percentage would read as covering all of them. When
    the window could not be read the line says nothing, since the line above has
    already said why and two of four lines on one sentence is a waste of the panel.
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


def lines(standing: data.Standing, width: int) -> list[Text]:
    """Render the whole panel, one line per fact.

    The median line is dropped rather than left as a bare label when the window
    could not be read, since the line above has already said why.
    """
    out = [share_text(standing, width), gpu_text(standing, width), states_text(standing, width)]
    if not standing.note:
        out.append(efficiency_text(standing, width))
    return out


def _fit(text: Text, width: int) -> Text:
    """Cut a line to the width it is drawn in, marking the cut.

    The other two panels mark theirs, and the tail here is usually a number: a
    fairshare score cropped to 0. reads as complete and is the exact value the
    warning color exists for.
    """
    room = max(width, 1)
    if len(text.plain) > room:
        text.truncate(max(room - 1, 0), overflow="crop")
        text.append("…")
    return text


class StandingPanel(VerticalScroll):
    """Fairshare, the GPU cap, and how the caller's recent jobs went.

    Holds its last figures when a read fails, and keeps the share and the cap when
    only the efficiency half is unavailable, since those are cheap and are what a
    user checks most.
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

    def begin_read(self) -> None:
        """Say that a read is under way, keeping the border and the last figures."""
        self._reading = True
        self.border_title = f"{TITLE} (reading)"
        self._paint()

    def end_read(self) -> None:
        """Clear the reading mark if it is still set, whatever ended the read."""
        if self._reading:
            self._reading = False
            self.border_title = f"{TITLE} (stale)" if self._error else TITLE
            self._paint()

    def show(self, standing: data.Standing) -> None:
        """Replace the panel with these figures."""
        self._standing, self._error, self._reading = standing, "", False
        self.border_title = TITLE
        self._paint()

    def fail(self, reason: str) -> None:
        """Mark the panel stale, naming the cause and keeping whatever it held."""
        self._error, self._reading = reason, False
        self.border_title = f"{TITLE} (stale)"
        self._paint()

    def on_resize(self, _event) -> None:
        self._paint()

    def _paint(self) -> None:
        body = self.query_one("#standing-body", Static)
        width = max(self.content_size.width - 1, 12)
        blocks: list[Text] = []
        if self._error:
            blocks.append(_fit(Text(f"stale: {self._error}", style="dim"), width))
        if self._standing is None:
            if not self._error:
                blocks.append(_fit(Text("reading your standing", style="dim"), width))
        else:
            if self._reading:
                blocks.append(_fit(Text("reading your standing", style="dim"), width))
            blocks.extend(lines(self._standing, width))
        body.update(Text("\n", no_wrap=True, overflow="crop").join(blocks))
