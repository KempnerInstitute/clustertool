"""gpu monitor-job command."""

import os
import pwd

import click

from clustertool import completion, monitor, slurm
from clustertool.grouping import keywords


@keywords("watch", "live", "realtime", "dashboard")
@click.command("monitor-job")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
@click.option(
    "--interval",
    type=click.IntRange(min=1),
    default=5,
    show_default=True,
    help="Seconds to wait between rounds of samples.",
)
def monitor_job(jobid: str, interval: int) -> None:
    """Live GPU/CPU/memory/InfiniBand monitor for a running job's nodes.

    Refreshes a colored per-node table in place until Ctrl+C. Requires
    passwordless ssh to the job's nodes, which must expose nvidia-smi.

    \b
    Use cases:
      - Watch GPU and network utilization across a multi-node job.
      - Confirm every node of a job is actually busy.

    \b
    Inputs:
      JOBID       Slurm job id of a running job.
      --interval  Seconds to wait between rounds (default 5). A round itself
                  takes a few seconds, so the period is longer than this.
    """
    owner = slurm.job_owner(jobid)
    me = pwd.getpwuid(os.getuid()).pw_name
    if owner and owner != me:
        raise click.ClickException(
            f"job {jobid} belongs to {owner}, not you. Node login is gated on having "
            "an allocation there, so this would be refused on every node; monitor one "
            "of your own jobs instead"
        )
    hosts = slurm.job_nodes(jobid)
    if not hosts:
        raise click.ClickException(f"no nodes found for job '{jobid}' (is it running?)")
    monitor.run_monitor(f"GPU/CPU/MEM/NET Monitor for SLURM Job: {jobid}", hosts, interval)
