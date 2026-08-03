"""What the dashboard's keys do, and how each one is described before it is done.

The mutating four go through clustertool.jobaction, the same planner the jobs
cancel, hold, release and requeue commands use, so the dashboard refuses the same
jobs for the same reasons. It runs the planned command captured rather than
through process.passthrough, whose inherited stdio would write over the screen.
"""

import dataclasses

from clustertool import jobaction, process
from clustertool.process import CommandError
from clustertool.tui import data

RUN_TIMEOUT_S = 30


@dataclasses.dataclass(frozen=True)
class Action:
    """One mutating key: what it is called, and what it costs to get wrong."""

    key: str
    name: str
    question: str
    caution: str = ""


MUTATING = (
    Action("c", "cancel", "Cancel this job?", "It stops now and cannot be resumed."),
    Action("h", "hold", "Hold this job?", "It stays queued but will not be scheduled."),
    Action("H", "release", "Release this job?", "It becomes eligible to start again."),
    Action(
        "ctrl+r",
        "requeue",
        "Requeue this job?",
        "It restarts from the beginning and the work so far is discarded.",
    ),
)
"""The keys that change a job, each behind a confirmation that defaults to No.

Requeue is on ctrl+r rather than the plan's q: q sits one shift away from Q, which
quits, and a key that throws away a running job's work should not be a slip of the
shift key from the one that leaves. r is already refresh, so plain letters are
taken; ctrl+r keeps the mnemonic without the adjacency.
"""

BY_KEY = {action.key: action for action in MUTATING}


def describe(action: Action, row: data.JobRow) -> str:
    """Return what the modal says about the job this action would act on.

    Names the job, where it runs and how long it has been going, because a
    confirmation that does not identify its target is not one.
    """
    where = row.nodelist if row.assigned else row.state
    return f"{row.jobid}  {row.state}  on {row.partition}  {where}  after {row.elapsed}"


def run(name: str, jobid: str) -> str:
    """Do the action and return the line the banner shows.

    Raises CommandError when the action is refused or fails, so a caller can put
    the reason on the banner unchanged. The command is captured rather than
    inherited: passthrough writes to the terminal the app is drawing on.
    """
    planned = jobaction.plan(name, [jobid])
    code, out, err = process.probe(planned.cmd, timeout=RUN_TIMEOUT_S)
    if code == 0:
        return f"{name} {jobid}: done"
    detail = (err.strip() or out.strip()).splitlines()
    raise CommandError(f"{detail[0]}" if detail else planned.failure)


UNSTARTED = "4294967294"
"""What Slurm substitutes for an array task id that has not been assigned yet.

jobs log names the same constant. A path holding it points at no file, so reading
it would report a missing file rather than a job that has not begun.
"""

LOG_LINES = 40
"""How much of a job's output the detail pane shows.

Enough to see what a job is doing or how it failed, and little enough that the
pane does not become the whole screen.
"""


def log_tail(jobid: str, lines: int = LOG_LINES) -> str:
    """Return the end of a job's output, or say why there is none to show.

    The path comes from the same helper jobs log uses, which asks the controller
    first and accounting second, so a job recent enough for either is covered.
    """
    from clustertool import slurm

    path, _ = slurm.job_output_paths(jobaction.checkable(jobid))
    if not path:
        return f"no output file recorded for {jobid}"
    if UNSTARTED in path:
        return f"{jobid} has not started, so its output file does not exist yet"
    code, out, err = process.probe(["tail", "-n", str(lines), path], timeout=RUN_TIMEOUT_S)
    if code != 0:
        return f"could not read {path}: {err.strip() or code}"
    return out.rstrip() or f"{path} is empty so far"


WHY_FIELD_NAMES = ("JobArrayID", "State", "Reason", "PriorityLong")
"""The squeue fields the why key reads, in the order it asks for them."""

WHY_FIELDS = ",".join(f"{name}:|" for name in WHY_FIELD_NAMES)

WHY_ROWS = 6
"""How many array elements the why key describes before it counts the rest.

An array can hold thousands, and squeue prints a row for each: one job's answer
would otherwise be a page of them.
"""

GONE = "Invalid job id"
"""What squeue says, on stderr and with a nonzero exit, for an id it does not hold.

A finished job is dropped by the controller MinJobAge seconds after it ends, so
this is the ordinary answer for a job that has just completed, not a fault.
"""


def why(jobid: str) -> str:
    """Return why a job is not running, from the controller's own reason and priority."""
    code, out, err = process.probe(
        [
            "squeue",
            "-t",
            "all",
            "-h",
            "-j",
            jobaction.checkable(jobid),
            "--Format=" + WHY_FIELDS,
        ],
        timeout=RUN_TIMEOUT_S,
    )
    if code != 0:
        if GONE in err:
            return f"{jobid} is no longer in the queue"
        return f"could not ask about {jobid}: {err.strip() or code}"
    rows = [line.split("|") for line in out.splitlines() if line.strip()]
    if not rows:
        return f"{jobid} is no longer in the queue"
    return "\n".join(_one_why(row) for row in rows[:WHY_ROWS]) + (
        f"\n...and {len(rows) - WHY_ROWS} more elements" if len(rows) > WHY_ROWS else ""
    )


def _one_why(row: list[str]) -> str:
    """Describe one queue row: what state it is in, and what is holding it.

    Read by position against WHY_FIELDS with an explicit separator, because a
    reason such as ReqNodeNotAvail, UnavailableNodes:... contains spaces and
    splitting on whitespace put the priority where the reason belonged.
    """
    field = dict(zip(WHY_FIELD_NAMES, (part.strip() for part in row), strict=False))
    jobid = field.get("JobArrayID") or "?"
    state = (field.get("State") or "").lower()
    reason = field.get("Reason") or ""
    priority = field.get("PriorityLong") or ""
    if state.startswith("running"):
        return f"{jobid} is running; nothing is holding it"
    if reason in ("", "None"):
        return f"{jobid} is {state}, at priority {priority}"
    return f"{jobid} is {state} because {reason}, at priority {priority}"


FOLLOW_INTERVAL_S = 2.0
"""How often a followed log is reread.

Slower than the jobs timer: a log grows at whatever rate the job writes, and
rereading the tail is a file read per tick.
"""


def _state_words(state: str) -> str:
    """Return a sacct state as plain words, without the uid sacct appends.

    sacct writes CANCELLED by 11222, which names a uid nobody reads, and the
    project spells the state canceled in prose.
    """
    head = state.split()[0].lower() if state.split() else state.lower()
    return "canceled" if head == "cancelled" else head


def scope(jobid: str) -> str:
    """Return one job's utilization, from the same blob the standing panel reads.

    jobstats writes the figures into the job's AdminComment, so a finished job
    carries its own efficiency and no extra service has to be asked.
    """
    from jobscope import blob

    code, out, err = process.probe(
        [
            "sacct",
            "-j",
            jobid,
            "-X",
            "-P",
            "-n",
            "--units=G",
            "-o",
            "State,Elapsed,AdminComment",
        ],
        timeout=RUN_TIMEOUT_S,
    )
    if code != 0:
        return f"could not read accounting for {jobid}: {err.strip() or code}"
    row = next((line.split("|") for line in out.splitlines() if line.strip()), [])
    if len(row) < 3:
        return f"accounting has nothing for {jobid} yet"
    state, elapsed, comment = _state_words(row[0]), row[1], row[2]
    stats = blob.decode_admin_comment(comment) if comment.strip() else None
    metrics = blob.blob_metrics(stats) if stats else None
    if metrics is None:
        return f"{jobid} is {state} after {elapsed}; no utilization recorded yet"
    cpu, mem, gpu, gmem = metrics
    parts = [f"cpu {cpu}%", f"mem {mem}%"]
    if gpu is not None:
        parts.append(f"gpu {gpu}%")
    if gmem is not None:
        parts.append(f"gpu mem {gmem}%")
    return f"{jobid} {state} after {elapsed}: " + "  ".join(parts)
