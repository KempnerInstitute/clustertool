"""The me dashboard application."""

from textual.app import App, ComposeResult
from textual.widgets import Static

from clustertool.tui import data


class MeApp(App):
    """One screen showing where the caller stands on the cluster."""

    TITLE = "clustertool me"
    BINDINGS = [("Q", "quit", "quit"), ("ctrl+c", "quit", "quit")]

    def __init__(self, identity: data.Identity | None = None) -> None:
        super().__init__()
        self._identity = identity or data.identity()

    def compose(self) -> ComposeResult:
        who = self._identity
        name = f" ({who.full_name})" if who.full_name else ""
        yield Static(f"{who.user}{name} @ {who.host}   {who.site_name}", id="status")


def run(identity: data.Identity | None = None) -> None:
    """Start the dashboard, returning when the user quits."""
    MeApp(identity=identity).run()
