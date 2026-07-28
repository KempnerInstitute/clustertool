"""jobs submit command."""

import click

from cluster_tools import process
from cluster_tools.grouping import keywords


@keywords("run", "launch")
@click.command(
    "submit",
    context_settings={"ignore_unknown_options": True, "help_option_names": []},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED, metavar="[ARG]...")
def submit(args: tuple[str, ...]) -> None:
    """Submit a batch job (passthrough to sbatch).

    All arguments are forwarded to sbatch unchanged, so a script path, --wrap,
    array, dependency, and mail flags all work. Run 'sbatch --help' for the
    full list.

    \b
    Most useful:
      jobs submit job.sh
      jobs submit -p kempner_h100 --account=LAB --gres=gpu:1 -t 0-01:00 job.sh
      jobs submit --array=1-10 job.sh

    \b
    Inputs:
      [ARG]...  Any sbatch arguments (script path, --wrap, directives), forwarded verbatim.
    """
    code = process.stream(["sbatch", *args])
    if code:
        raise SystemExit(code)
