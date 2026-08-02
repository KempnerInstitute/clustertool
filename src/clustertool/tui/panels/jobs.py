"""The jobs panel and the detail pane beneath it."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from clustertool.tui import data

COLUMNS = (
    ("ID", 12, 18),
    ("PART", 6, 13),
    ("ST", 2, 2),
    ("GPU", 3, 3),
    ("ELAP", 7, 10),
    ("NODE", 6, 20),
)
"""Each column as (heading, narrowest useful width, width worth growing to).

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

NODES_IN_DETAIL = 240
"""Longest node list shown in full in the detail pane.

A 200-node allocation writes a hostlist several hundred characters long, which
fills the pane and pushes the TRES out of it.
"""


def elide(text: str, width: int) -> str:
    """Return text no wider than width, marking a cut with an ellipsis."""
    if width < 1 or len(text) <= width:
        return text
    return text[: width - 1] + "…"


def layout(width: int) -> list[tuple[str, int]]:
    """Return the columns that fit in width, and how wide each cell may be.

    Drops whole columns before it lets the remaining ones fall below the width at
    which they say anything, then shares what is left over round by round, so no
    single column takes all the slack.
    """
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
        growable = [name for name, _, high in columns if widths[name] < high]
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

    def compose(self) -> ComposeResult:
        table = DataTable(id="jobs-table", cursor_type="row", zebra_stripes=False)
        yield table
        yield Static("", id="jobs-detail")

    def on_mount(self) -> None:
        self.border_title = TITLE

    def on_resize(self, _event) -> None:
        """Lay the columns out again, since how many fit depends on the width."""
        self._paint()

    def show(self, rows: list[data.JobRow]) -> None:
        """Replace the table with these rows, keeping the cursor on the same job."""
        previous = self.selected.jobid if self.selected else None
        self._error = ""
        self.border_title = TITLE
        self._paint(rows, previous)

    def _paint(self, rows: list[data.JobRow] | None = None, previous: str | None = None) -> None:
        """Draw the table at the current width, restoring the cursor onto previous."""
        table = self.query_one("#jobs-table", DataTable)
        if rows is None:
            rows, previous = self._rows, self.selected.jobid if self.selected else None
        columns = layout(table.size.width or 80)
        table.clear(columns=True)
        table.add_columns(*(name for name, _ in columns))
        for row in rows:
            cells = self._cells(row)
            table.add_row(*(elide(cells[name], width) for name, width in columns), key=row.jobid)
        self._rows = rows
        if previous is not None:
            for index, row in enumerate(rows):
                if row.jobid == previous:
                    table.move_cursor(row=index)
                    break
        self._refresh_detail()

    @staticmethod
    def _cells(row: data.JobRow) -> dict[str, str]:
        """Return the row keyed by column heading, so a dropped column just goes unread."""
        return {
            "ID": row.jobid,
            "PART": row.partition,
            "ST": row.code,
            "GPU": str(row.gpus) if row.gpus else "-",
            "ELAP": row.elapsed,
            "NODE": row.where,
        }

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
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        self.query_one("#jobs-detail", Static).update(self._detail_text())

    def _detail_text(self) -> str:
        parts = []
        if self._error:
            parts.append(f"stale: {self._error}")
        row = self.selected
        if row is None:
            parts.append(EMPTY if not self._error else "")
        else:
            parts.append(f"{row.jobid}  {row.state}  on {row.partition}")
            if row.pending:
                parts.append(f"waiting: {row.reason}")
            parts.append(f"holds: {row.tres or 'nothing recorded'}")
            parts.append(f"nodes: {_nodes(row)}")
        return "\n".join(p for p in parts if p)


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
