"""gpu pulse command."""

import os
import pwd
import shlex
import sys

import click

from clustertool import process, site, slurm
from clustertool.grouping import keywords


def _split_args(args: tuple[str, ...]) -> tuple[str | None, str | None, list[str], bool]:
    """Pull --node / --job / --dry-run out of the passthrough args.

    Returns (node, job, forwarded_args, dry_run); everything else is forwarded
    to kempnerpulse unchanged.
    """
    node = job = None
    dry_run = False
    forward: list[str] = []
    items = iter(args)
    for arg in items:
        if arg in ("--node", "--job"):
            value = next(items, None)
            if value is None or value.startswith("-"):
                raise click.UsageError(f"{arg} needs a value")
            if arg == "--node":
                node = value
            else:
                job = value
        elif arg.startswith("--node="):
            node = arg.split("=", 1)[1]
        elif arg.startswith("--job="):
            job = arg.split("=", 1)[1]
        elif arg == "--dry-run":
            dry_run = True
        elif arg == "--wrapper-help":
            click.echo(_WRAPPER_HELP)
            raise SystemExit(0)
        else:
            forward.append(arg)
    if node is not None and not node:
        raise click.UsageError("--node needs a value")
    if job is not None and not job:
        raise click.UsageError("--job needs a value")
    if node and job:
        raise click.UsageError("give --node or --job, not both")
    if dry_run and not (node or job):
        raise click.UsageError("--dry-run prints the remote command, so it needs --node or --job")
    return node, job, forward, dry_run


_WRAPPER_HELP = """Options this wrapper handles itself, rather than forwarding:

  --node NODE     Run the dashboard on NODE over ssh.
  --job JOBID     Run it on the first node of one of your own running jobs.
  --dry-run       Print the ssh command instead of running it.
  --wrapper-help  Show this text.

Everything else goes to the pulse tool unchanged. --help reaches it, not this
wrapper, so it lists that tool's own options."""


def _remote_command(venv: str, tool: str, args: list[str]) -> str:
    """Build the shell command that runs the pulse tool from a venv on a GPU node."""
    check = (
        "command -v nvidia-smi >/dev/null 2>&1 || "
        "{ echo 'no nvidia-smi on the target node' >&2; exit 1; }"
    )
    activate = shlex.quote(f"{venv}/bin/activate")
    forward = " ".join(shlex.quote(arg) for arg in args)
    return f"{check}; source {activate} && exec {shlex.quote(tool)} {forward}".rstrip()


@keywords("dcgm", "realtime", "monitor", "htop", "remote")
@click.command(
    "pulse",
    context_settings={"ignore_unknown_options": True, "help_option_names": []},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED, metavar="[ARG]...")
def pulse(args: tuple[str, ...]) -> None:
    """Live GPU utilization dashboard, via the bundled kempnerpulse tool.

    All arguments are forwarded to kempnerpulse unchanged, so its full option set
    is available. '--help' reaches kempnerpulse, not this wrapper, so it lists
    kempnerpulse's options; run 'gpu pulse --wrapper-help' for --node, --job and
    --dry-run, which are this wrapper's own.

    Run it on a GPU node, or launch it on a remote node with --node NODE (or --job
    JOBID to target a running job's first node): this tool ssh's in and runs
    kempnerpulse from the site's shared install. --dry-run prints the ssh command
    instead of running it. --job accepts only your own job. --node names any node,
    but where node login requires an allocation there, as pam_slurm_adopt
    enforces, the ssh is refused unless you hold one.

    \b
    Most useful:
      gpu pulse                        live dashboard on this node
      gpu pulse --node holygpu123      dashboard on a remote node
      gpu pulse --job 1234567          dashboard on a job's node
      gpu pulse --once                 render one snapshot and exit

    For completed-job efficiency use 'jobs scope' instead.
    """
    node, job, forward, dry_run = _split_args(args)
    if job and not node:
        owner = slurm.job_owner(job)
        me = pwd.getpwuid(os.getuid()).pw_name
        if owner and owner != me:
            raise click.ClickException(
                f"job {job} belongs to {owner}, not you. Node login is gated on having "
                "an allocation there, so the ssh would be refused"
            )
        nodes = slurm.job_nodes(job)
        if not nodes:
            raise click.ClickException(f"job {job} has no running nodes")
        node = nodes[0]

    if not node:
        raise SystemExit(process.stream([sys.executable, "-m", "kempnerpulse", *forward]))

    venv = site.pulse_remote_venv()
    if not venv:
        raise click.ClickException(
            "remote pulse is not configured for this site; set [pulse].remote_venv"
        )
    ssh_cmd = [
        "ssh",
        "-tt",
        "-o",
        "StrictHostKeyChecking=accept-new",
        node,
        "bash",
        "-lc",
        shlex.quote(_remote_command(venv, site.pulse_remote_tool(), forward)),
    ]
    if dry_run:
        click.echo(" ".join(ssh_cmd))
        return
    raise SystemExit(process.stream(ssh_cmd))
