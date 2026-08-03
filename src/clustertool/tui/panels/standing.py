"""The standing panel: fairshare, the GPU cap, and how recent work went."""

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from clustertool.tui import data, styles

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


def share_style(score: str, color: bool = True) -> str:
    """Return the style for a fairshare score, empty when it is unremarkable.

    A score below a half means the account has used more than its share and its
    jobs will start behind others, which is the one thing worth a color here.
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

    Both, because either can be what stops the next job starting, and they are
    different limits. Reading a user's own usage against the account cap, which is
    six times larger here, said they had room they did not have.

    A count that could not be read says so rather than showing zero against the
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


IDLE_WARN = 50
IDLE_BAD = 75


def idle_style(unused: int, color: bool = True) -> str:
    """Return the style for the unused share, which is the point of showing it."""
    if unused >= IDLE_BAD:
        return styles.resolve(styles.ALARM, color)
    return styles.resolve(styles.WARN, color) if unused >= IDLE_WARN else ""


def unused_text(standing: data.Standing, width: int, color: bool = True) -> Text:
    """Render how much of the GPU time the caller held went unused.

    The median utilization is honest but is not the figure that changes what anyone
    does: a median over jobs counts a one-minute job and a two-day one the same. This
    weights by the time held, so it says what the cluster lost. For this caller's
    last week the median GPU utilization was 8% while 88% of the 34 GPU-hours they
    held went unused.

    The coverage is part of the figure, as it is on the median line: fewer than half
    of this caller's GPU jobs carry utilization data at all, and the total would
    read as covering all of them.
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

    The median line is dropped rather than left as a bare label when the window
    could not be read, since the line above has already said why. The unused line
    goes when no GPU job of the caller's was measured, which is every job for
    someone who runs none: a label with nothing after it says less than no line.
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
"""How much of a failure the border title names before the panel stops quoting it.

The title is a border, so Textual cuts what will not fit. Six words is what a
narrow panel shows of a reason, and the reason's first words are the ones that say
what happened.
"""


def _stale_title(reason: str) -> str:
    """Return the border title for a panel whose figures are old, naming the cause.

    On the title rather than in the body because the body has no row to spare, and
    a mark that says only stale leaves a reader with nothing to act on.
    """
    said = " ".join(reason.split()[:TITLE_REASON_WORDS])
    return f"{TITLE} (stale: {said})" if said else f"{TITLE} (stale)"


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
            self.border_title = _stale_title(self._error) if self._error else TITLE
            self._paint()

    def show(self, standing: data.Standing) -> None:
        """Replace the panel with these figures."""
        self._standing, self._error, self._reading = standing, "", False
        self.border_title = TITLE
        self._paint()

    def fail(self, reason: str) -> None:
        """Mark the panel stale, naming the cause and keeping whatever it held.

        The cause goes on the border title, not on a line of the body: the panel has
        five rows for its five facts, so a line here pushed the fifth out of sight,
        which is the same row the reading mark used to cost. The title is also the
        one part of a panel a short terminal does not clip.
        """
        self._error, self._reading = reason, False
        self.border_title = _stale_title(reason)
        self._paint()

    def on_resize(self, _event) -> None:
        self._paint()

    def _paint(self) -> None:
        """Draw the panel, using every row it has for figures.

        Neither the reading mark nor the stale reason takes a line while there are
        figures to show: the border title carries both, and the panel has exactly as
        many rows as it has facts, so either one pushed the last fact out of sight.
        With no figures yet there is nothing to push, and the body says what is
        happening instead.
        """
        body = self.query_one("#standing-body", Static)
        width = max(self.content_size.width - 1, 12)
        blocks: list[Text] = []
        if self._standing is None:
            said = f"stale: {self._error}" if self._error else "reading your standing"
            blocks.append(_fit(Text(said, style="dim"), width))
        else:
            blocks.extend(lines(self._standing, width, not self.app.no_color))
        body.update(Text("\n", no_wrap=True, overflow="crop").join(blocks))
