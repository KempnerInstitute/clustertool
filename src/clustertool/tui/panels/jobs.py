"""The jobs panel and the detail pane beneath it."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from clustertool.tui import data

COLUMNS = (("ID", 18), ("PART", 13), ("ST", 2), ("GPU", 3), ("ELAP", 10), ("NODE", 20))
"""Column headings and the width each cell is cut to.

A partition list, and a pending reason such as ReqNodeNotAvail with its node
list, both run long enough on their own to push the table past any terminal, and
the table cannot scroll usefully because a refresh resets the offset. The full
value is in the detail pane, which wraps.
"""

TITLE = "Jobs"

EMPTY = "No jobs of yours are queued or running."


def elide(text: str, width: int) -> str:
    """Return text no wider than width, marking a cut with an ellipsis."""
    if width < 1 or len(text) <= width:
        return text
    return text[: width - 1] + "…"


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
        table.add_columns(*(name for name, _ in COLUMNS))
        yield table
        yield Static("", id="jobs-detail")

    def on_mount(self) -> None:
        self.border_title = TITLE

    def show(self, rows: list[data.JobRow]) -> None:
        """Replace the table with these rows, keeping the cursor on the same job."""
        table = self.query_one("#jobs-table", DataTable)
        previous = self.selected.jobid if self.selected else None
        self._rows = rows
        self._error = ""
        self.border_title = TITLE
        table.clear()
        for row in rows:
            cells = (
                row.jobid,
                row.partition,
                row.code,
                str(row.gpus) if row.gpus else "-",
                row.elapsed,
                row.where,
            )
            table.add_row(
                *(elide(cell, width) for cell, (_, width) in zip(cells, COLUMNS, strict=True)),
                key=row.jobid,
            )
        if previous is not None:
            for index, row in enumerate(rows):
                if row.jobid == previous:
                    table.move_cursor(row=index)
                    break
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
            where = row.nodelist if row.assigned else "not assigned"
            parts.append(f"{row.jobid}  {row.state}  on {row.partition}")
            if row.pending:
                parts.append(f"waiting: {row.reason}")
            parts.append(f"nodes: {where}")
            parts.append(f"holds: {row.tres or 'nothing recorded'}")
        return "\n".join(p for p in parts if p)
