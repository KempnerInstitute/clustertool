"""The jobs panel and the detail pane beneath it."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from clustertool.tui import data

COLUMNS = ("ID", "PART", "ST", "GPU", "ELAP", "NODE")

EMPTY = "No jobs of yours are queued or running."


class JobsPanel(Vertical):
    """The caller's jobs, with the selected one described below the table.

    Holds its last good rows when a refresh fails, so a scheduler hiccup leaves
    the panel stale rather than empty, which would read as having no jobs.
    """

    def __init__(self) -> None:
        super().__init__(id="jobs", classes="panel")
        self._rows: list[data.JobRow] = []
        self._error = ""

    def compose(self) -> ComposeResult:
        table = DataTable(id="jobs-table", cursor_type="row", zebra_stripes=False)
        table.add_columns(*COLUMNS)
        yield table
        yield Static("", id="jobs-detail")

    def show(self, rows: list[data.JobRow]) -> None:
        """Replace the table with these rows, keeping the cursor where it can."""
        self._rows = rows
        self._error = ""
        table = self.query_one("#jobs-table", DataTable)
        previous = self.selected.jobid if self.selected else None
        table.clear()
        for row in rows:
            table.add_row(
                row.jobid,
                row.partition,
                _short_state(row.state),
                str(row.gpus) if row.gpus else "-",
                row.elapsed,
                row.where,
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
            where = ", ".join(row.nodes) if row.nodes else "not assigned"
            parts.append(f"{row.jobid}  {row.state}  on {row.partition}")
            if row.pending:
                parts.append(f"waiting: {row.reason}")
            parts.append(f"nodes: {where}")
            parts.append(f"holds: {row.tres or 'nothing recorded'}")
        return "\n".join(p for p in parts if p)


def _short_state(state: str) -> str:
    """Return Slurm's own two-letter form, which is what squeue prints in %t."""
    words = state.split()
    head = words[0] if words else ""
    return {
        "RUNNING": "R",
        "PENDING": "PD",
        "COMPLETING": "CG",
        "CONFIGURING": "CF",
        "SUSPENDED": "S",
        "COMPLETED": "CD",
        "CANCELLED": "CA",
        "FAILED": "F",
        "TIMEOUT": "TO",
        "PREEMPTED": "PR",
        "NODE_FAIL": "NF",
        "OUT_OF_MEMORY": "OOM",
    }.get(head, head[:3])
