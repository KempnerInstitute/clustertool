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


JOB_FIELDS = (
    "JobArrayID:|,StateCompact:|,State:|,Partition:|,TimeUsed:|,"
    "Reason:|,tres-alloc:|,NodeList:|,NumNodes:|"
)
"""The one squeue format the panel reads.

JobArrayID rather than JobID: JobID prints the internal numeric id, which for an
array element is neither what the user submitted nor what scancel and the rest of
the CLI print. JobArrayID matched %i on every one of the 16,759 jobs queued when
this was checked. StateCompact rather than deriving the two-letter code here,
which is Slurm's table to own. NumNodes so the node column can name the head and
a count without expanding the hostlist, which costs a scontrol fork per job.
"""

PENDING_CODES = ("PD", "CF")

EMPTY_NODELISTS = ("", "none assigned", "none", "(null)")


@dataclasses.dataclass(frozen=True)
class JobRow:
    """One of the caller's jobs, as the panel shows it."""

    jobid: str
    code: str
    state: str
    partition: str
    gpus: int
    elapsed: str
    reason: str
    nodelist: str
    nnodes: int
    tres: str

    @property
    def pending(self) -> bool:
        """True while the job is waiting rather than running."""
        return self.code in PENDING_CODES

    @property
    def assigned(self) -> bool:
        """True once Slurm has named nodes for the job."""
        return self.nodelist.strip().lower() not in EMPTY_NODELISTS

    @property
    def where(self) -> str:
        """The node column: where it runs, or why it is not running yet."""
        if self.assigned:
            from clustertool import slurm

            head = slurm.first_node(self.nodelist)
            return head if self.nnodes <= 1 else f"{head} +{self.nnodes - 1}"
        return f"({self.reason})" if self.reason and self.reason != "None" else "-"


def _count(text: str) -> int:
    """Return a squeue count field as an int, tolerating the range a pending job shows."""
    head = text.split("-")[0].strip()
    return int(head) if head.isdigit() else 0


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
    if code == 127:
        raise CommandError("'squeue' not found on this host")
    if code == 124:
        raise CommandError("squeue timed out; the controller is not answering")
    if code != 0:
        raise CommandError(f"could not read your jobs: {err.strip() or code}")
    rows = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) < 9:
            continue
        jobid, short, state, partition, elapsed, reason, tres, nodelist, nnodes = (
            p.strip() for p in parts[:9]
        )
        if not jobid:
            continue
        rows.append(
            JobRow(
                jobid=jobid,
                code=short,
                state=state,
                partition=partition,
                gpus=slurm.parse_gpu_count(tres),
                elapsed=elapsed,
                reason=reason,
                nodelist=nodelist,
                nnodes=_count(nnodes),
                tres=tres,
            )
        )
    return rows
