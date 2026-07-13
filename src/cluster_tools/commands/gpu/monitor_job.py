"""gpu monitor-job command."""

import click

from cluster_tools import monitor, slurm


@click.command("monitor-job")
@click.argument("jobid")
@click.option("--interval", default=5, show_default=True, help="Refresh interval in seconds.")
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
      --interval  Refresh interval in seconds (default 5).
    """
    hosts = slurm.job_nodes(jobid)
    if not hosts:
        raise click.ClickException(f"no nodes found for job '{jobid}' (is it running?)")
    monitor.run_monitor(f"GPU/CPU/MEM/NET Monitor for SLURM Job: {jobid}", hosts, interval)
