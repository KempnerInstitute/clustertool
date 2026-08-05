"""jobs release command."""

import click

from clustertool import completion, jobaction, process
from clustertool.grouping import keywords


@keywords("unhold", "unblock", "resume", "unfreeze")
@click.command("release")
@click.argument(
    "jobids",
    nargs=-1,
    required=True,
    metavar="JOBID...",
    shell_complete=completion.complete_job_ids,
)
def release(jobids: tuple[str, ...]) -> None:
    """Release held jobs so they can be scheduled (via scontrol release).

    Undoes 'jobs hold'. Per man scontrol the rule is the kind of hold, not who
    placed it: an owner or an account coordinator may release a user-hold, while
    only a privileged user may release an admin-hold. Note that 'jobs hold' run
    by an operator or admin records an admin-hold the owner cannot lift, which
    scontrol uhold exists to avoid.

    \b
    Use cases:
      - Let a previously held job start.

    \b
    Inputs:
      JOBID...  One or more Slurm job ids.
    """
    if any(not jobid.strip() for jobid in jobids):
        raise click.UsageError("JOBID may not be empty.")
    planned = jobaction.plan("release", list(jobids))
    process.passthrough(planned.cmd, planned.failure)
