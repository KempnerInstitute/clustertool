"""Console-script entry point.

Importing the command tree reads the site config, so an unusable config fails at
import. The import happens behind a guard that reports it as a CLI error.
"""

from clustertool.site import ConfigError


def _load_main():
    """Import and return the CLI group."""
    from clustertool.cli import main

    return main


def run() -> None:
    """Run the CLI, reporting an unusable site config without a traceback."""
    try:
        main = _load_main()
    except ConfigError as exc:
        raise SystemExit(f"clustertool: error: {exc}") from exc
    main()
