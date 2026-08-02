"""Interactive dashboard for the me command.

Imported only when the optional tui extra is installed and stdout is a terminal.
The me command must not import this at module scope, so a site without the extra
keeps the one-shot output and the dependency stays optional.
"""

from clustertool.tui.app import run

__all__ = ["run"]
