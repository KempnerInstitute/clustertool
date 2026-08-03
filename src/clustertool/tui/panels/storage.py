"""The storage panel: home, lab quotas worst first, and the caller's own usage."""

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from clustertool.tui import data

TITLE = "Storage"

BAR_WIDTH = 6

PERCENT_WIDTH = 5

WARN_AT = 0.75
FULL_AT = 0.90
"""Where a bar turns.

A quota is not a problem until it is nearly reached, and a lab that has reached
one has already stopped being able to write, so the two thresholds are the only
distinctions worth a color.
"""

FILLED, EMPTY_CELL = "█", "░"

NO_LABS = "No lab directories found for you."


def bar(fraction: float | None, width: int = BAR_WIDTH) -> str:
    """Return a usage bar, or spaces when there is no quota to be a fraction of.

    To the nearest cell rather than rounded up. Six cells is coarse, and rounding
    up filled every one of them from 84%, which made a directory with room left
    look exactly like one that had stopped being able to write. Any usage at all
    still shows a cell, since an empty bar for a directory holding data is worse
    than no bar.
    """
    if fraction is None or width < 1:
        return " " * max(width, 0)
    filled = min(width, max(0, round(fraction * width)))
    if fraction > 0 and filled == 0:
        filled = 1
    return FILLED * filled + EMPTY_CELL * (width - filled)


def style_for(fraction: float | None) -> str:
    """Return the style for a usage figure, empty when it is unremarkable."""
    if fraction is None:
        return "dim"
    if fraction >= FULL_AT:
        return "bold red"
    if fraction >= WARN_AT:
        return "yellow"
    return ""


BAR_NEEDS = PERCENT_WIDTH + BAR_WIDTH + 6
"""Narrowest row that still has room for a bar after a readable label.

Below it the bar is dropped rather than the percentage, which is the figure the
bar only illustrates. The panel's own width floor keeps rows at 22 or wider, so
this is a backstop against a future layout rather than a width the app reaches.
"""


def row_text(row: data.QuotaRow, width: int) -> Text:
    """Render one quota row as label, percent and bar, cut to width.

    Built as styled spans rather than as markup, because a label carries a group
    name from the filesystem and a bracket in one would otherwise be read as a
    markup tag. Truncated at the end as a backstop, so the row can never be wider
    than the column it is drawn in whatever the arithmetic above did.
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
    tail = PERCENT_WIDTH + (BAR_WIDTH + 1 if with_bar else 0)
    room = max(width - tail, 1)
    fraction = row.fraction
    shown = min(PERCENT_WIDTH, max(width - room, 1))
    text.append(_cut(row.label, room).ljust(room))
    text.append(f"{row.percent:>{shown}}", style=style_for(fraction))
    if with_bar:
        text.append(" ")
        text.append(bar(fraction), style=style_for(fraction))
    text.truncate(width, overflow="crop")
    return text


def lines(info: data.StorageInfo, width: int) -> list[Text]:
    """Render the whole panel, section by section, every line cut to width.

    The section headings are cut as well as the rows: they are the one text here
    that is not built to a width, and at the panel's floor they are wider than it.
    """
    out: list[Text] = []
    if info.home is not None:
        out.append(row_text(info.home, width))
        out.append(Text(""))
    out.append(Text(_cut(f"labs ({len(info.labs)}), fullest first", width), style="dim"))
    if info.labs:
        out.extend(row_text(row, width) for row in info.labs)
    else:
        out.append(Text(_cut(NO_LABS, width), style="dim"))
    if info.mine:
        out.append(Text(""))
        out.append(Text(_cut("you, on lustre", width), style="dim"))
        out.extend(row_text(row, width) for row in info.mine)
    return out


def _cut(text: str, width: int) -> str:
    """Return text no wider than width, marking a cut with an ellipsis."""
    if width < 1 or len(text) <= width:
        return text
    return text[: width - 1] + "…"


class StoragePanel(VerticalScroll):
    """Quotas for home, every lab directory, and the caller on Lustre.

    Scrolls, because a user can belong to twenty labs across four filesystems and
    the panel is a side column. Rows are ordered fullest first so the ones worth
    acting on are the ones on screen without scrolling.
    """

    def __init__(self) -> None:
        super().__init__(id="storage", classes="panel")
        self._info: data.StorageInfo | None = None
        self._error = ""

    def compose(self):
        yield Static("", id="storage-body")

    def on_mount(self) -> None:
        self.border_title = TITLE
        self.can_focus = True

    def show(self, info: data.StorageInfo) -> None:
        """Replace the panel with these figures."""
        self._info, self._error = info, ""
        self.border_title = TITLE
        self._paint()

    def fail(self, reason: str) -> None:
        """Mark the panel stale, naming the cause and keeping whatever it held."""
        self._error = reason
        self.border_title = f"{TITLE} (stale)"
        self._paint()

    def on_resize(self, _event) -> None:
        self._paint()

    def _paint(self) -> None:
        """Render the panel one line per row.

        A column is held back for the scrollbar whether or not one is showing, so
        a row does not wrap the moment the list grows past the panel.

        The no-wrap flag goes on the joined text rather than on the rows, since
        Text.join builds a fresh object from the separator and drops a flag set on
        the parts. It is a backstop: lines() already cuts every line to width, so
        nothing here should reach it. It stays because cropping is the safe way to
        be wrong about a width, and wrapping is not.
        """
        body = self.query_one("#storage-body", Static)
        width = max(self.content_size.width - 1, 12)
        blocks: list[Text] = []
        if self._error:
            blocks.append(Text(_cut(f"stale: {self._error}", width), style="dim"))
        if self._info is None:
            if not self._error:
                blocks.append(Text(_cut("reading quotas", width), style="dim"))
        else:
            blocks.extend(lines(self._info, width))
        body.update(Text("\n", no_wrap=True, overflow="crop").join(blocks))
