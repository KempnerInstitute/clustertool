"""The storage panel: home, lab quotas worst first, and the caller's own usage."""

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from clustertool.tui import data, styles

TITLE = "Storage"

BAR_WIDTH = 6

PERCENT_WIDTH = 5

FIGURE_WIDTH = 7
"""Widest figure a row can lead with.

A percentage needs four cells and an inode-bound one five, but a row with no quota
leads with the size it holds, which runs to seven.
"""

WARN_AT = 0.75
FULL_AT = 0.90
"""Where a bar turns: nearly full, and full enough that writes have stopped."""

FILLED, EMPTY_CELL = "█", "░"

NO_LABS = "No lab directories found for you."


def bar(fraction: float | None, width: int = BAR_WIDTH) -> str:
    """Return a usage bar, or spaces when there is no quota to be a fraction of.

    Rounded to the nearest cell rather than up, so a directory with room left does not
    look full. Any usage at all still shows one cell.
    """
    if fraction is None or width < 1:
        return " " * max(width, 0)
    filled = min(width, max(0, round(fraction * width)))
    if fraction > 0 and filled == 0:
        filled = 1
    return FILLED * filled + EMPTY_CELL * (width - filled)


def style_for(fraction: float | None, color: bool = True) -> str:
    """Return the style for a usage figure, empty when it is unremarkable."""
    if fraction is None:
        return "dim"
    if fraction >= FULL_AT:
        return styles.resolve(styles.ALARM, color)
    if fraction >= WARN_AT:
        return styles.resolve(styles.WARN, color)
    return ""


BAR_NEEDS = 30 + FIGURE_WIDTH - PERCENT_WIDTH
"""Narrowest row that still has room for a bar after a readable label.

Below it the bar goes rather than the label or the percentage, since the bar only
illustrates a number that is printed beside it.
"""


def row_text(row: data.QuotaRow, width: int, color: bool = True) -> Text:
    """Render one quota row as label, percent and bar, cut to width.

    Built as styled spans rather than markup, since a label carries a group name from
    the filesystem where a bracket would be read as a style tag. The final truncation
    is a backstop against the arithmetic above.
    """
    text = Text(no_wrap=True, overflow="crop")
    if width < 1:
        return text
    if row.error:
        room = max(width // 2, 4)
        text.append(_cut(row.label, room).ljust(room))
        text.append("  ")
        text.append(_cut(row.error, max(width - room - 2, 1)), style="dim")
        text.truncate(width, overflow="crop")
        return text
    with_bar = width >= BAR_NEEDS
    figure = _figure(row)
    shown = max(len(figure), PERCENT_WIDTH)
    tail = shown + 1 + (BAR_WIDTH + 1 if with_bar else 0)
    room = max(width - tail, 1)
    fraction = row.fraction
    text.append(_cut(row.label, room).ljust(room))
    text.append(" ")
    text.append(f"{_cut(figure, shown):>{shown}}", style=style_for(fraction, color))
    if with_bar:
        text.append(" ")
        text.append(bar(fraction), style=style_for(fraction, color))
    text.truncate(width, overflow="crop")
    return text


def _figure(row: data.QuotaRow) -> str:
    """Return the number a row leads with.

    The usage rather than a dash when no quota is set, since the per-user rows on
    Lustre carry none here. An i marks a row whose inode quota, not its block quota,
    is the one nearly reached.
    """
    if row.fraction is None:
        return row.used if row.used not in ("", "-") else "-"
    percent = row.files if row.files_bound else row.percent
    return f"{percent}i" if row.files_bound else percent


def lines(info: data.StorageInfo, width: int, color: bool = True) -> list[Text]:
    """Render the whole panel, section by section, every line cut to width.

    The section headings are cut as well as the rows: they are the one text here
    that is not built to a width, and at the panel's floor they are wider than it.
    """
    out: list[Text] = []
    if info.home is not None:
        out.append(row_text(info.home, width, color))
        out.append(Text(""))
    out.append(Text(_cut(_labs_heading(info.labs), width), style="dim"))
    if info.labs:
        out.extend(row_text(row, width, color) for row in info.labs)
    else:
        out.append(Text(_cut(NO_LABS, width), style="dim"))
    if info.mine:
        out.append(Text(""))
        out.append(Text(_cut("you, on lustre", width), style="dim"))
        out.extend(row_text(row, width, color) for row in info.mine)
    return out


def _labs_heading(labs: list[data.QuotaRow]) -> str:
    """Name the lab section, counting the rows that could not be read.

    A failure sorts to the top of the list, but a side column shows only its first
    dozen rows and the count is how the rest are accounted for.
    """
    failed = sum(1 for row in labs if row.error)
    if failed:
        return f"labs ({len(labs)}, {failed} unread), fullest first"
    return f"labs ({len(labs)}), fullest first"


def _cut(text: str, width: int) -> str:
    """Return text no wider than width, marking a cut with an ellipsis."""
    if width < 1 or len(text) <= width:
        return text
    return text[: width - 1] + "…"


class StoragePanel(VerticalScroll):
    """Quotas for home, every lab directory, and the caller on Lustre.

    Scrolls, since a user can belong to many labs across several filesystems. Rows are
    ordered fullest first, so the ones worth acting on need no scrolling.
    """

    def __init__(self) -> None:
        super().__init__(id="storage", classes="panel")
        self._info: data.StorageInfo | None = None
        self._error = ""
        self._reading = False

    def compose(self):
        yield Static("", id="storage-body")

    def on_mount(self) -> None:
        self.border_title = TITLE
        self.can_focus = True
        self._paint()

    def begin_read(self) -> None:
        """Say that a read is under way, keeping the border and the last figures.

        Textual's own loading flag replaces the whole widget, border and title
        included, which leaves a hole in the layout while the fan-out runs.
        """
        self._reading = True
        self.border_title = f"{TITLE} (reading)"
        self._paint()

    def end_read(self) -> None:
        """Clear the reading mark if it is still set, whatever ended the read.

        A worker canceled at teardown raises CancelledError, which is not an Exception,
        so neither the result nor the failure path runs.
        """
        if self._reading:
            self._reading = False
            self.border_title = f"{TITLE} (stale)" if self._error else TITLE
            self._paint()

    def show(self, info: data.StorageInfo) -> None:
        """Replace the panel with these figures."""
        self._info, self._error, self._reading = info, "", False
        self.border_title = TITLE
        self._paint()

    def fail(self, reason: str) -> None:
        """Mark the panel stale, naming the cause and keeping whatever it held."""
        self._error, self._reading = reason, False
        self.border_title = f"{TITLE} (stale)"
        self._paint()

    def on_resize(self, _event) -> None:
        self._paint()

    @property
    def ready(self) -> bool:
        """Whether this panel's own widgets exist yet.

        A query can land before Textual has mounted them, and looking one up then
        raises inside the worker whose job is to report failures.
        """
        return bool(self.query("#storage-body"))

    def _paint(self) -> None:
        """Render the panel one line per row.

        A column is held back for the scrollbar whether or not one is showing, so a
        row does not wrap the moment the list grows past the panel. The no-wrap flag
        goes on the joined text rather than the rows, since Text.join drops a flag set
        on the parts.
        """
        if not self.ready:
            return
        body = self.query_one("#storage-body", Static)
        width = max(self.content_size.width - 1, 12)
        blocks: list[Text] = []
        if self._error:
            blocks.append(Text(_cut(f"stale: {self._error}", width), style="dim"))
        if self._info is None:
            if not self._error:
                blocks.append(Text(_cut("reading quotas", width), style="dim"))
        else:
            if self._reading:
                blocks.append(Text(_cut("reading quotas", width), style="dim"))
            blocks.extend(lines(self._info, width, not self.app.no_color))
        body.update(Text("\n", no_wrap=True, overflow="crop").join(blocks))
