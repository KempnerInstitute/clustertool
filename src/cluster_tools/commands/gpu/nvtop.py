"""gpu nvtop command."""

import click

from cluster_tools import process, slurm
from cluster_tools.grouping import keywords

_SSH_OPTS = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -t"


def _build_session(session: str, hosts: list[str]) -> None:
    """Create a detached tmux session with one nvtop pane per host."""
    process.run(["tmux", "new-session", "-d", "-s", session, "-n", "nvtop"])
    for _ in hosts[1:]:
        process.run(["tmux", "split-window", "-t", f"{session}:0"])
        process.run(["tmux", "select-layout", "-t", f"{session}:0", "tiled"])
    panes = process.run(["tmux", "list-panes", "-t", f"{session}:0", "-F", "#P"]).split()
    for host, pane in zip(hosts, panes, strict=False):
        remote = (
            f"ssh {_SSH_OPTS} {host} "
            "'hostname; command -v nvtop >/dev/null && nvtop "
            '|| echo "nvtop not found"; exec bash\''
        )
        process.run(["tmux", "send-keys", "-t", f"{session}:0.{pane}", remote, "C-m"])
    process.run(["tmux", "select-layout", "-t", f"{session}:0", "tiled"])


@keywords("htop", "monitor", "watch", "live")
@click.command("nvtop")
@click.argument("jobid")
@click.option("--attach/--no-attach", default=True, help="Attach to the session after creating it.")
def nvtop(jobid: str, attach: bool) -> None:
    """Open a tmux session running nvtop on each of a job's nodes.

    Creates a tiled tmux session 'nvtop_<jobid>' with one pane per node, each
    ssh-ing to the node and launching nvtop. Requires tmux locally and
    passwordless ssh to the nodes.

    \b
    Use cases:
      - Watch per-node GPU activity for a multi-node job at a glance.

    \b
    Inputs:
      JOBID                 Slurm job id of a running job.
      --attach/--no-attach  Attach after creating the session (default attach).
    """
    hosts = slurm.job_nodes(jobid)
    if not hosts:
        raise click.ClickException(f"no nodes found for job '{jobid}' (is it running?)")
    session = f"nvtop_{jobid}"
    _build_session(session, hosts)
    if attach:
        process.stream(["tmux", "attach", "-t", session])
    else:
        click.echo(
            f"tmux session '{session}' ready with {len(hosts)} pane(s). "
            f"Attach with: tmux attach -t {session}"
        )
