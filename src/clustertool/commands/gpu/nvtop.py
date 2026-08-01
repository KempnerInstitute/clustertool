"""gpu nvtop command."""

import os

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords

_SSH_OPTS = "-o StrictHostKeyChecking=accept-new -t"


def _build_session(session: str, hosts: list[str]) -> None:
    """Create a detached tmux session with one nvtop pane per host.

    Refuses an existing session rather than splitting panes into it, which would
    leave the caller's earlier session holding both sets.
    """
    code, _, err = process.probe(["tmux", "new-session", "-d", "-s", session, "-n", "nvtop"])
    if code:
        raise click.ClickException(
            f"could not create tmux session '{session}': {err.strip() or code}. "
            f"If it already exists, attach with 'tmux attach -t {session}' or remove "
            f"it with 'tmux kill-session -t {session}'"
        )
    for _ in hosts[1:]:
        process.run(["tmux", "split-window", "-t", f"{session}:0"])
        process.run(["tmux", "select-layout", "-t", f"{session}:0", "tiled"])
    panes = process.run(["tmux", "list-panes", "-t", f"{session}:0", "-F", "#P"]).split()
    if len(panes) < len(hosts):
        click.echo(
            f"warning: tmux gave {len(panes)} pane(s) for {len(hosts)} host(s); "
            "the terminal may be too small to split further",
            err=True,
        )
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
@click.argument("jobid", shell_complete=completion.complete_job_ids)
@click.option("--attach/--no-attach", default=True, help="Attach to the session after creating it.")
def nvtop(jobid: str, attach: bool) -> None:
    """Open a tmux session running nvtop on each of a job's nodes.

    Creates a tiled tmux session 'nvtop_<jobid>' with one pane per node, each
    ssh-ing to the node and launching nvtop. Requires tmux locally and passwordless
    ssh to the nodes. Where node login requires an allocation on the node, as
    pam_slurm_adopt enforces, this works only for your own running job; other
    people's nodes refuse the login and their panes show the refusal.

    \b
    Use cases:
      - Watch per-node GPU activity for a multi-node job at a glance.

    \b
    Inputs:
      JOBID                 Slurm job id of a running job.
      --attach/--no-attach  Attach after creating the session (default attach).
    """
    owner = slurm.job_owner(jobid)
    me = os.environ.get("USER", "")
    if owner and me and owner != me:
        raise click.ClickException(
            f"job {jobid} belongs to {owner}, not you. Node login is gated on having "
            "an allocation there, so this would be refused on every node; monitor one "
            "of your own jobs instead"
        )
    hosts = slurm.job_nodes(jobid)
    if not hosts:
        raise click.ClickException(f"no nodes found for job '{jobid}' (is it running?)")
    session = f"nvtop_{jobid}"
    _build_session(session, hosts)
    if attach:
        process.stream(["tmux", "attach", "-t", session])
    else:
        click.echo(f"tmux session '{session}' ready. Attach with: tmux attach -t {session}")
