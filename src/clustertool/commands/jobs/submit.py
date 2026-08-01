"""jobs submit command."""

import click

from clustertool import process
from clustertool.grouping import keywords


@keywords("run", "launch")
@click.command(
    "submit",
    context_settings={"ignore_unknown_options": True, "help_option_names": []},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED, metavar="[ARG]...")
def submit(args: tuple[str, ...]) -> None:
    """Submit a batch job (passthrough to sbatch).

    All arguments are forwarded to sbatch unchanged, so a script path, --wrap,
    array, dependency, and mail flags all work. Run 'sbatch --help' for the full
    list. sbatch's own exit code is passed through, so this can stand in for sbatch
    in a script. '--help' is forwarded too, so it prints sbatch's help rather than
    this text; 'clustertool jobs --help' and docs/commands/jobs.md are where the
    wrapper's own description lives.

    \b
    Most useful:
      jobs submit job.sh
      jobs submit -p PARTITION --account=LAB --gres=gpu:1 -t 0-01:00 job.sh
      jobs submit --array=1-10 job.sh

    \b
    Inputs:
      [ARG]...  Any sbatch arguments (script path, --wrap, directives), forwarded verbatim.
    """
    code = process.stream(["sbatch", *args])
    if code:
        raise SystemExit(code)
