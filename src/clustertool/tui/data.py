"""Panel data, gathered without any reference to the widgets that show it.

Each function returns a plain dataclass so it can be tested without starting an
app, which is where the parsing and failure handling are covered.
"""

import dataclasses
import os
import pwd
import socket

from clustertool import site
from clustertool.process import CommandError


@dataclasses.dataclass(frozen=True)
class Identity:
    """Who is running the app, and where."""

    user: str
    full_name: str
    host: str
    site_name: str


def identity() -> Identity:
    """Return the caller's identity from the uid, never from the environment.

    The site name rather than the QoS cluster, which the site config documents as
    the cluster the admin qos commands write to and which would label every
    deployment with the packaged default.
    """
    from clustertool import slurm

    user = pwd.getpwuid(os.getuid()).pw_name
    try:
        full = slurm.user_fullnames([user]).get(user, "")
    except CommandError:
        full = ""
    return Identity(
        user=user,
        full_name=full,
        host=socket.gethostname().split(".")[0],
        site_name=site.site_name(),
    )


JOB_FIELDS = "JobID:|,State:|,Partition:|,TimeUsed:|,Reason:|,tres-alloc:|,NodeList:|"

PENDING_STATES = ("PENDING", "CONFIGURING")


@dataclasses.dataclass(frozen=True)
class JobRow:
    """One of the caller's jobs, as the panel shows it."""

    jobid: str
    state: str
    partition: str
    gpus: int
    elapsed: str
    reason: str
    nodes: list[str]
    tres: str

    @property
    def pending(self) -> bool:
        """True while the job is waiting rather than running."""
        return self.state.startswith(PENDING_STATES)

    @property
    def where(self) -> str:
        """The node column: where it runs, or why it is not running yet."""
        if self.nodes:
            head = self.nodes[0]
            return head if len(self.nodes) == 1 else f"{head} +{len(self.nodes) - 1}"
        return f"({self.reason})" if self.reason and self.reason != "None" else "-"


def jobs(user: str) -> list[JobRow]:
    """Return the caller's jobs in one squeue call.

    The allocated TRES rather than the requested, since Slurm rounds a request up
    to a whole node or socket and the panel should show what the job holds. The
    field separator is asked for explicitly, because the default format pads to
    fixed widths and truncates a long TRES string.
    """
    from clustertool import process, slurm

    code, out, err = process.probe(
        ["squeue", "-h", "-u", user, "--Format=" + JOB_FIELDS], timeout=30
    )
    if code != 0:
        raise CommandError(f"could not read your jobs: {err.strip() or code}")
    rows = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) < 7:
            continue
        jobid, state, partition, elapsed, reason, tres, nodelist = (p.strip() for p in parts[:7])
        if not jobid:
            continue
        rows.append(
            JobRow(
                jobid=jobid,
                state=state,
                partition=partition,
                gpus=slurm.parse_gpu_count(tres),
                elapsed=elapsed,
                reason=reason,
                nodes=slurm.expand_hostlist(nodelist),
                tres=tres,
            )
        )
    return rows
