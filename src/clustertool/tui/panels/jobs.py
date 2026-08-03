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

The ceilings are the widest value each field takes across every queued job, so a
wide terminal spends its room on the table rather than leaving it blank. ELAP is
the one that has to be right: every other field is repeated in full in the detail
pane, so eliding it there costs nothing but a keystroke, and 11 covers
DD-HH:MM:SS to 99 days.

A partition list, and a pending reason such as ReqNodeNotAvail with its node
list, both run long enough on their own to push the table past any terminal, and
the table cannot scroll usefully because a refresh resets the offset. So cells
are cut to fit. Cut to a width computed from the terminal, not to a constant: a
constant sized for a wide terminal is chopped by the viewport on a narrower one,
which loses the ellipsis and leaves a fragment reading as a whole value. The full
value is in the detail pane, which wraps.
"""

DROP_ORDER = ("NODE", "PART", "ELAP", "GPU")
"""Which column to give up first when even the narrow widths do not fit.

ID and ST are never dropped: which job, and whether it is running, are the two
things the panel exists to say.
"""

CELL_PADDING = 2
"""Columns each side of a DataTable cell, which the widths have to pay for."""

TITLE = "Jobs"

EMPTY = "No jobs of yours are queued or running."

DETAIL_CEILING = 8
"""The max-height of the detail pane in app.tcss, in rows of its region."""

TABLE_FLOOR = 2
"""The min-height of the table in app.tcss, which the pane cannot take from."""

DETAIL_TRIM = 1
"""Rows of the pane's region that are not a line of text: its dashed border-top.

Its top padding is the other, and that is what the tight class takes away: with it
the pane paints one line fewer than it measures, and that line was the last of a
read.
"""


def pane_rows(content_height: int) -> int:
    """Return how many lines of text the detail pane paints in a panel this tall.

    The pane cannot scroll: it takes no focus and the arrow keys belong to the
    table, so a line past its edge is one nobody can read. Everything the pane
    shows is budgeted against this count.

    A constant here was wrong, and wrong in the direction that loses lines. The
    panel is a third of a stacked layout on a narrow terminal and the whole of a
    side-by-side one, so its height varies by a factor of three; a budget of five
    overran a pane that had room for two and left two rows of a pane that had room
    for seven blank. The arithmetic is the layout's own: the table keeps its
    minimum, the pane takes what is left up to its ceiling, and one row of that
    goes on the border rather than on text. It is checked against the painted
    frame rather than trusted, since the three numbers it uses live in the
    stylesheet.

    Nought is a real answer, and rounding it up to one is how this went wrong the
    first time. Below fifteen rows of terminal the whole of the pane's region is its
    border, and a budget of one put a line where no line is painted.
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

    Cells rather than code points, and tabs expanded first, because the renderer
    measures in cells and this is what makes one line of a read one row. Counted by
    code point, a line of Japanese that fitted took two rows and a tab took up to
    eight, so the row budget was wrong by however many such lines there were and the
    last line of a log went missing at every terminal size, not only short ones.
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


def ceilings(rows: list[data.JobRow]) -> dict[str, int]:
    """Return how wide each column may grow for these rows, its own rule permitting.

    A column grown past the widest value it holds takes that width from one that had
    to be cut. At 100 columns ID took 18 cells for a 9-character id while NODE was
    cut to 9 of the 47 its value needed, because the static ceiling is the widest
    value the field takes across every job on the cluster rather than across the
    ones on screen. The heading counts, since a column narrower than its own
    heading cuts that instead.

    The cost is that the columns move when the data does: one pending array
    element with a folded id widens ID for as long as it is queued. That is the
    trade, and it is the right way round, because a width that shifts is still
    readable and a value cut to a fragment is not.

    No rows means no constraint rather than the headings alone. An empty table has
    no value to fit, and a caller asking what the table may do without naming any
    rows is asking about the widest it goes.
    """
    if not rows:
        return {name: high for name, _, high in COLUMNS}
    values = [cells(row) for row in rows]
    return {
        name: min(high, max([cell_len(name), *(cell_len(value[name]) for value in values)]))
        for name, _, high in COLUMNS
    }


def layout(width: int, rows: list[data.JobRow] | None = None) -> list[tuple[str, int]]:
    """Return the columns that fit in width, and how wide each cell may be.

    Drops whole columns before it lets the remaining ones fall below the width at
    which they say anything, then shares what is left over round by round, so no
    single column takes all the slack. Width left over once every column holds its
    own widest value is left unspent rather than padding the columns out to the
    panel's edge.
    """
    grown = ceilings(rows or [])
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

    Holds its last good rows when a refresh fails, so a scheduler hiccup leaves
    the panel stale rather than empty, which would read as having no jobs. The
    stale mark goes on the border title as well as into the detail, because the
    detail is the first thing a short terminal clips.
    """

    def __init__(self) -> None:
        super().__init__(id="jobs", classes="panel")
        self._rows: list[data.JobRow] = []
        self._error = ""
        self._extra = ""
        self._extra_for = ""
        self._columns: list[tuple[str, int]] = []

    def compose(self) -> ComposeResult:
        table = DataTable(id="jobs-table", cursor_type="row", zebra_stripes=False)
        yield table
        yield Static("", id="jobs-detail", markup=False)

    def on_mount(self) -> None:
        self.border_title = TITLE

    def on_resize(self, _event) -> None:
        """Lay the columns out again, since how many fit depends on the width.

        Only when the layout actually changed. Dragging a window edge delivers an
        event per column, and rebuilding the table costs about 70ms for someone
        holding four thousand jobs, most of it in add_row. Redrawing on a stale
        layout instead of skipping is not an option: the old widths no longer fit,
        and the overflow would be clipped without an ellipsis.
        """
        table = self.query_one("#jobs-table", DataTable)
        if layout(table.size.width or 80, self._rows) != self._columns:
            self._paint()
        elif self._extra:
            self._refresh_detail()

    def show(self, rows: list[data.JobRow]) -> None:
        """Replace the table with these rows, keeping the cursor on the same job."""
        previous = self.selected.jobid if self.selected else None
        self._error = ""
        self.border_title = TITLE
        self._paint(rows, previous)

    def _paint(self, rows: list[data.JobRow] | None = None, previous: str | None = None) -> None:
        """Draw the table at the current width, restoring the cursor onto previous.

        Each column is given its width outright rather than left to size itself
        from its content. An automatic width is recomputed on a later refresh, so
        after a resize the table painted every column at its heading width, with
        cells chopped to it and no ellipsis, until something else forced a redraw.
        """
        table = self.query_one("#jobs-table", DataTable)
        if rows is None:
            rows, previous = self._rows, self.selected.jobid if self.selected else None
        columns = layout(table.size.width or 80, rows)
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

        Remembered against the job it describes, which the caller names, because a
        read that lands after the cursor has moved would otherwise be stamped with
        whatever is selected then and shown under the wrong job indefinitely.

        Keeping it at all is what lets it survive a refresh of the rows; it goes
        when the cursor moves to a different job. Clearing it on any highlight event
        wiped a log tail every five seconds, which is to say before it could be read.
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

        That padding separates the detail from the dashed rule above it, and it is a
        row of the pane's region: with it a pane five rows tall paints four lines. It
        goes exactly when what the pane holds would not otherwise fit, which is a
        read at any size and the plain detail on a short terminal. At seventy
        columns by sixteen rows the pane has one row for text, the padding was it,
        and the pane showed nothing at all.
        """
        detail = self.query_one("#jobs-detail", Static)
        text = self._detail_text()
        detail.set_class(len(text.splitlines()) >= pane_rows(self.content_size.height), "tight")
        detail.update(text)

    def _detail_text(self) -> str:
        """Render the pane, showing a read only under the job it was taken from."""
        parts = []
        if self._error:
            parts.append(f"stale: {self._error}")
        row = self.selected
        if row is None:
            parts.append(EMPTY if not self._error else "")
        else:
            parts.append(f"{row.jobid}  {row.state}  on {row.partition}")
            if row.pending and row.stated_reason:
                parts.append(f"waiting: {row.stated_reason}")
            parts.append(f"elapsed: {row.elapsed}")
            parts.append(f"holds: {row.tres or 'nothing recorded'}")
            parts.append(f"nodes: {_nodes(row)}")
        if self._extra and row is not None and row.jobid == self._extra_for:
            taken = self._reading_text(row)
            if taken:
                return taken
            parts.append(self._extra)
        return "\n".join(p for p in parts if p)

    def _reading_text(self, row: data.JobRow) -> str:
        """Render the pane while it carries a read, keeping the read's last lines.

        A read of one line, which is what the why and scope keys give, is added to
        the detail: taking the whole pane over for it would cost the elapsed time,
        the TRES and the nodes to show a single sentence. A longer one does take the
        pane, because the two together are more lines than there is room for, and
        then one line names the job so the read cannot be mistaken for another's.

        Every row the pane will spend is counted, and every line it shows is cut to
        the pane's width so that one line is one row, the stale mark included.
        Counting logical lines instead lost the last one three times over: to the
        stale mark being a row at all, to a traceback line naming an absolute path
        wrapping onto two, and to the stale message itself wrapping at 46 and 80
        columns once everything else had been cut.

        What the rows are spent on, in the order the last one is given up: the read's
        final line, which is what a caller pressed the key for; the line naming the
        job; how many lines were dropped; the stale mark, which is on the border
        title as well; and then the earlier lines of the read. A pane with no room
        for the count says it on the end of the job line instead, and a pane of one
        row marks it with a leading ellipsis on the line itself, so that a cut is
        marked at every size rather than only at the comfortable ones.
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
        elif dropped and top:
            top[-1] += f"  (+{dropped} earlier)"
        elif dropped:
            kept = [f"…{kept[0]}"]
        return "\n".join(elide(line, width) for line in [*top, *kept])


def _nodes(row: data.JobRow) -> str:
    """Describe where a job runs, cut short before it can fill the pane.

    The TRES line comes first and the node list last, because a wide allocation
    writes a hostlist long enough to push everything after it off the pane, and of
    the two the TRES is the one that does not grow with the job.
    """
    if not row.assigned:
        return "not assigned"
    listed = elide(row.nodelist, NODES_IN_DETAIL)
    return f"{row.nnodes} on {listed}" if row.nnodes > 1 else listed
