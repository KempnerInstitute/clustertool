"""gpu session command."""

import click

from cluster_tools import process


@click.command("session")
@click.option("-A", "--account", required=True, help="Fairshare account to charge.")
@click.option("-p", "--partition", default="kempner", show_default=True, help="Partition.")
@click.option("-g", "--gpus", type=int, default=1, show_default=True, help="GPUs to request.")
@click.option("-c", "--cpus", type=int, default=16, show_default=True, help="CPUs to request.")
@click.option("-m", "--mem", default="64G", show_default=True, help="Memory to request.")
@click.option(
    "-t", "--time", "time_limit", default="0-01:00", show_default=True, help="Time limit (D-HH:MM)."
)
@click.option("--constraint", default=None, help="Node feature constraint (e.g. a100).")
def session(
    account: str,
    partition: str,
    gpus: int,
    cpus: int,
    mem: str,
    time_limit: str,
    constraint: str | None,
) -> None:
    """Start an interactive GPU session (via salloc).

    Allocates GPUs on a partition with Kempner defaults and drops you into a
    shell on the node. Requires your fairshare --account. Exit the shell (or let
    the time limit lapse) to release the allocation.

    \b
    Use cases:
      - Grab a GPU for interactive development or debugging.

    \b
    Inputs:
      -A, --account    Fairshare account to charge (required).
      -p, --partition  Partition (default kempner).
      -g, --gpus       GPUs to request (default 1).
      -c, --cpus       CPUs to request (default 16).
      -m, --mem        Memory (default 64G).
      -t, --time       Time limit D-HH:MM (default 0-01:00).
      --constraint     Node feature constraint (e.g. a100).
    """
    cmd = [
        "salloc",
        "-p",
        partition,
        "--account=" + account,
        "--gres=gpu:" + str(gpus),
        "--cpus-per-task=" + str(cpus),
        "--mem=" + mem,
        "-t",
        time_limit,
    ]
    if constraint:
        cmd.append("--constraint=" + constraint)
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
