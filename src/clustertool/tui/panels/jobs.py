"""The jobs panel and the detail pane beneath it."""

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from clustertool.tui import actions, data

COLUMNS = (
    ("ID", 12, 31),
    ("PART", 6, 50),
    ("ST", 2, 2),
    ("GPU", 3, 3),
    ("ELAP", 7, 11),
    ("NODE", 6, 47),
)
"""Each column as (heading, narrowest useful width, widest worth growing to).

The minimum is the width at which a column still says something; the ceiling is the
widest value the field takes across every job on the cluster, so ELAP's 11 covers
DD-HH:MM:SS to 99 days. A cell wider than its column is cut with an ellipsis, and
the full value is shown in the detail pane, which wraps.
"""

DROP_ORDER = ("NODE", "PART", "ELAP", "GPU")
"""Which column to give up first when even the narrow widths do not fit.

ID and ST are absent because which job it is, and whether it is running, are the two
things the panel exists to say.
"""

CELL_PADDING = 2
"""Columns each side of a DataTable cell, which the widths have to pay for."""

TITLE = "Jobs"

EMPTY = "No jobs of yours are queued or running."

DETAIL_ORDER = ("stale", "job", "waiting", "elapsed", "holds", "nodes", "read")
"""The lines of the plain detail, in the order the pane shows them."""

DETAIL_PRIORITY = ("read", "job", "waiting", "nodes", "holds", "elapsed", "stale")
"""The same lines in the order they are given up when the pane is short of rows.

Highest first. The read leads because a caller asked for it; the elapsed time and
the stale mark come last because the table and the border title carry them.
"""

DETAIL_CEILING = 8
"""The max-height of the detail pane in app.tcss, in rows of its region."""

TABLE_FLOOR = 2
"""The min-height of the table in app.tcss, which the pane cannot take from."""

DETAIL_TRIM = 1
"""Rows of the pane's region that hold no text: its dashed border-top.

Its top padding is the other, which the tight class removes when the pane needs
that row for a line.
"""


def pane_rows(content_height: int) -> int:
    """Return how many lines of text the detail pane paints in a panel this tall.

    The table keeps its minimum height, the pane takes what is left up to its
    ceiling, and one row of that is its border. The pane cannot scroll, so
    everything it shows is budgeted against this count. Zero is a valid answer: on a
    terminal under about fifteen rows the pane is all border and paints nothing.
    """
    return max(min(DETAIL_CEILING, content_height - TABLE_FLOOR) - DETAIL_TRIM, 0)


NODES_IN_DETAIL = 240
"""Longest node list shown in full in the detail pane.

A 200-node allocation writes a hostlist several hundred characters long, which
fills the pane and pushes the TRES out of it.
"""


TAB_WIDTH = 8
"""How wide a tab is taken to be, matching the usual terminal default."""


def elide(text: str, width: int) -> str:
    """Return text no wider than width display cells, marking a cut with an ellipsis.

    Cells rather than code points, and tabs expanded first, since that is how the
    renderer measures: it is what makes one line one row.
    """
    flat = text.expandtabs(TAB_WIDTH)
    if width < 1 or cell_len(flat) <= width:
        return flat
    kept = ""
    for char in flat:
        if cell_len(kept) + cell_len(char) > width - 1:
            break
        kept += char
    return kept + "…"


def wrapped(text: str, width: int) -> list[str]:
    """Return text as the rows it takes at this width, measured in display cells.

    Wrapped rather than cut, since the pane is where a value too long for its column
    is read in full. Wrapped here rather than by the renderer because the pane
    budgets in rows and has to know how many a line will take. A word wider than the
    width is folded, and the fold always advances by at least one character, so a
    width of zero or one cannot loop.
    """
    flat = text.expandtabs(TAB_WIDTH)
    if width < 1:
        return [flat]
    rows: list[str] = []
    row = ""
    for word in flat.split(" "):
        joined = f"{row} {word}" if row else word
        if cell_len(joined) <= width:
            row = joined
            continue
        if row:
            rows.append(row)
            row = ""
        while word and cell_len(word) > width:
            head = ""
            for char in word:
                if head and cell_len(head) + cell_len(char) > width:
                    break
                head += char
            rows.append(head)
            word = word[len(head) :]
        row = word
    if row or not rows:
        rows.append(row)
    return rows


def ceilings(rows: list[data.JobRow]) -> dict[str, int]:
    """Return how wide each column may grow for these rows, capped by COLUMNS.

    A column grown past the widest value it holds takes width from one that had to
    be cut, so the ceiling is what the rows on screen need. The columns therefore
    move when the data does. With no rows the static ceilings apply, since there is
    no value to fit.
    """
    if not rows:
        return {name: high for name, _, high in COLUMNS}
    values = [cells(row) for row in rows]
    return {
        name: min(high, max(cell_len(value[name]) for value in values)) for name, _, high in COLUMNS
    }


def layout(width: int, grown: dict[str, int] | None = None) -> list[tuple[str, int]]:
    """Return the columns that fit in width, and how wide each cell may be.

    Drops whole columns before letting the rest fall below their minimums, then
    shares what is left round by round so no single column takes all the slack.
    Width left over once every column holds its widest value is unspent.

    Takes the ceilings rather than the rows: a resize asks this once per column
    dragged, and walking every row to answer would cost more than the repaint it
    exists to avoid.
    """
    if grown is None:
        grown = ceilings([])
    columns = list(COLUMNS)
    for name in DROP_ORDER:
        if _needs(columns) <= width or len(columns) <= 2:
            break
        columns = [column for column in columns if column[0] != name]
    widths = {name: low for name, low, _ in columns}
    deficit = _needs(columns) - width
    while deficit > 0:
        widest = max(columns, key=lambda column: widths[column[0]])
        if widths[widest[0]] <= 1:
            break
        widths[widest[0]] -= 1
        deficit -= 1
    spare = width - _needs(columns)
    while spare > 0:
        growable = [name for name, _, _ in columns if widths[name] < grown[name]]
        if not growable:
            break
        for name in growable:
            if spare <= 0:
                break
            widths[name] += 1
            spare -= 1
    return [(name, widths[name]) for name, _, _ in columns]


def _needs(columns: list[tuple[str, int, int]]) -> int:
    """Return the width the columns take at their narrowest, padding included."""
    return sum(low for _, low, _ in columns) + CELL_PADDING * len(columns)


def cells(row: data.JobRow) -> dict[str, str]:
    """Return the row keyed by column heading, so a dropped column just goes unread."""
    return {
        "ID": row.jobid,
        "PART": row.partition,
        "ST": row.code,
        "GPU": str(row.gpus) if row.gpus else "-",
        "ELAP": row.elapsed,
        "NODE": row.where,
    }


class JobsPanel(Vertical):
    """The caller's jobs, with the selected one described below the table.

    Keeps its last good rows when a refresh fails and marks itself stale, since an
    empty table would read as having no jobs.
    """

    def __init__(self) -> None:
        super().__init__(id="jobs", classes="panel")
        self._rows: list[data.JobRow] = []
        self._error = ""
        self._extra = ""
        self._extra_for = ""
        self._columns: list[tuple[str, int]] = []
        self._grown: dict[str, int] = ceilings([])

    def compose(self) -> ComposeResult:
        table = DataTable(id="jobs-table", cursor_type="row", zebra_stripes=False)
        yield table
        yield Static("", id="jobs-detail", markup=False)

    def on_mount(self) -> None:
        self.border_title = TITLE

    def on_resize(self, _event) -> None:
        """Lay the columns out again, since how many fit depends on the width.

        The table is rebuilt only when the layout changed, because a drag delivers an
        event per column and a rebuild is expensive for a caller with thousands of
        jobs. The detail is repainted either way, since its row budget depends on the
        height that this event also carries.
        """
        table = self.query_one("#jobs-table", DataTable)
        if layout(table.size.width or 80, self._grown) != self._columns:
            self._paint()
        else:
            self._refresh_detail()

    def show(self, rows: list[data.JobRow]) -> None:
        """Replace the table with these rows, keeping the cursor on the same job."""
        previous = self.selected.jobid if self.selected else None
        self._error = ""
        self.border_title = TITLE
        self._paint(rows, previous)

    def _paint(self, rows: list[data.JobRow] | None = None, previous: str | None = None) -> None:
        """Draw the table at the current width, restoring the cursor onto previous.

        Each column is given its width outright: an automatic width is recomputed on
        a later refresh, which leaves cells chopped to the heading width.
        """
        table = self.query_one("#jobs-table", DataTable)
        if rows is None:
            rows, previous = self._rows, self.selected.jobid if self.selected else None
        self._grown = ceilings(rows)
        columns = layout(table.size.width or 80, self._grown)
        self._columns = columns
        table.clear(columns=True)
        for name, width in columns:
            table.add_column(name, width=width)
        for row in rows:
            value = cells(row)
            table.add_row(*(elide(value[name], width) for name, width in columns), key=row.jobid)
        self._rows = rows
        if previous is not None:
            for index, row in enumerate(rows):
                if row.jobid == previous:
                    table.move_cursor(row=index)
                    break
        self._refresh_detail()

    def show_text(self, text: str, jobid: str) -> None:
        """Add something read off the cluster below the detail.

        Remembered against the job the caller named, so a read that lands after the
        cursor has moved is not shown under another job. It survives a refresh of the
        rows and goes when the cursor moves to a different job.
        """
        self._extra = actions.printable(text)
        self._extra_for = jobid
        self._refresh_detail()

    def fail(self, reason: str) -> None:
        """Mark the panel stale, naming the cause and keeping whatever it held."""
        self._error = reason
        self.border_title = f"{TITLE} (stale)"
        self._refresh_detail()

    @property
    def selected(self) -> data.JobRow | None:
        """The row under the cursor, or None when the table is empty."""
        table = self.query_one("#jobs-table", DataTable)
        if not self._rows or table.cursor_row < 0:
            return None
        if table.cursor_row >= len(self._rows):
            return None
        return self._rows[table.cursor_row]

    def on_data_table_row_highlighted(self, _event: DataTable.RowHighlighted) -> None:
        row = self.selected
        if row is None or row.jobid != self._extra_for:
            self._extra, self._extra_for = "", ""
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        """Repaint the detail pane, giving up its top padding when the lines need the row.

        The padding separates the detail from the rule above it and costs a row of
        the pane, so it goes exactly when the content would not otherwise fit.
        """
        detail = self.query_one("#jobs-detail", Static)
        text = self._detail_text()
        detail.set_class(len(text.splitlines()) >= pane_rows(self.content_size.height), "tight")
        detail.update(text)

    def _detail_text(self) -> str:
        """Render the pane, showing a read only under the job it was taken from.

        Budgeted against the rows the pane paints, so a one-line answer from the why
        or scope key is not clipped on a short terminal.
        """
        row = self.selected
        said = {}
        if self._error:
            said["stale"] = f"stale: {self._error}"
        if row is None:
            said["job"] = EMPTY if not self._error else ""
        else:
            said["job"] = f"{row.jobid}  {row.state}  on {row.partition}"
            if row.pending and row.stated_reason:
                said["waiting"] = f"waiting: {row.stated_reason}"
            said["elapsed"] = f"elapsed: {row.elapsed}"
            said["holds"] = f"holds: {row.tres or 'nothing recorded'}"
            said["nodes"] = f"nodes: {_nodes(row)}"
        if self._extra and row is not None and row.jobid == self._extra_for:
            taken = self._reading_text(row)
            if taken:
                return taken
            said["read"] = self._extra
        return self._fit_detail({name: text for name, text in said.items() if text})

    def _fit_detail(self, said: dict[str, str]) -> str:
        """Keep as many of the pane's facts as it has rows for, wrapping each to width.

        Rows rather than lines, since a wrapped pending reason takes three of them.
        Facts are taken in DETAIL_PRIORITY order, and the one the rows run out on
        keeps what is left rather than being dropped whole. A cut is marked with an
        ellipsis at the front of the first row, where eliding cannot remove it.
        """
        width = max(self.query_one("#jobs-detail", Static).content_size.width, 8)
        budget = max(pane_rows(self.content_size.height), 1)
        kept: dict[str, list[str]] = {}
        cut = False
        for name in sorted(said, key=DETAIL_PRIORITY.index):
            room = budget - sum(len(rows) for rows in kept.values())
            if room < 1:
                cut = True
                break
            rows = wrapped(said[name], width)
            if len(rows) > room:
                rows, cut = rows[:room], True
            kept[name] = rows
        shown = [row for name in DETAIL_ORDER if name in kept for row in kept[name]]
        if cut and shown:
            shown[0] = elide(f"…{shown[0]}", width)
        return "\n".join(shown)

    def _reading_text(self, row: data.JobRow) -> str:
        """Render the pane while it carries a read, keeping the read's last lines.

        A one-line read, which is what the why and scope keys give, is added to the
        detail instead; a longer one takes the pane and names its job.

        Every line is cut to the pane's width so one line is one row, and the rows go
        to the read's final line first, then the job line, the count of lines dropped,
        the stale mark, and the earlier lines of the read. With no room for the count,
        the cut is marked with a leading ellipsis on the oldest line shown.
        """
        lines = [line for line in self._extra.splitlines() if line.strip()]
        if len(lines) <= 1:
            return ""
        width = max(self.query_one("#jobs-detail", Static).content_size.width, 8)
        budget = pane_rows(self.content_size.height)
        if budget < 1:
            return elide(lines[-1], width)
        top = []
        if budget >= 2:
            top.append(f"{row.jobid}  {row.state}  on {row.partition}")
            budget -= 1
        if self._error and budget >= 2:
            top.insert(0, f"stale: {self._error}")
            budget -= 1
        kept = lines[-budget:]
        dropped = len(lines) - len(kept)
        if dropped and budget >= 2:
            kept = lines[-(budget - 1) :]
            top.append(f"...{len(lines) - len(kept)} earlier lines not shown")
        elif dropped:
            kept = [f"…{kept[0]}", *kept[1:]]
        return "\n".join(elide(line, width) for line in [*top, *kept])


def _nodes(row: data.JobRow) -> str:
    """Describe where a job runs, cut short before it can fill the pane.

    A wide allocation writes a hostlist several hundred characters long, so the node
    list is shown after the TRES and truncated.
    """
    if not row.assigned:
        return "not assigned"
    listed = elide(row.nodelist, NODES_IN_DETAIL)
    return f"{row.nnodes} on {listed}" if row.nnodes > 1 else listed
