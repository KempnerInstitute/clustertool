"""Console-script entry point.

Importing the command tree reads the site config, because a few commands build
their choices from it at decoration time. A broken config therefore fails during
import, before click can turn it into a clean message, so the import happens here
behind a guard.
"""

from clustertool.site import ConfigError


def _load_main():
    """Import and return the CLI group, reading the site config as a side effect."""
    from clustertool.cli import main

    return main


def run() -> None:
    """Run the CLI, reporting an unusable site config without a traceback."""
    try:
        main = _load_main()
    except ConfigError as exc:
        raise SystemExit(f"clustertool: error: {exc}") from exc
    main()
