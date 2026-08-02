"""Console-script entry point.

Importing the command tree reads the site config, so an unusable config fails at
import. The import happens behind a guard that reports it as a CLI error.
"""

import signal

from clustertool.site import ConfigError


def _load_main():
    """Import and return the CLI group."""
    from clustertool.cli import main

    return main


def _restore_sigpipe() -> None:
    """Die on a closed pipe the way the Slurm tools do.

    Python ignores SIGPIPE and raises BrokenPipeError instead, which click
    reports as exit 1, so piping into head or less would look like a failure.
    Restoring the default disposition gives the shell's 141, matching squeue.
    """
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def run() -> None:
    """Run the CLI, reporting an unusable site config without a traceback."""
    _restore_sigpipe()
    try:
        main = _load_main()
    except ConfigError as exc:
        raise SystemExit(f"clustertool: error: {exc}") from exc
    main()
