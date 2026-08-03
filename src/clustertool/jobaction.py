"""Checks and command construction for the actions that change a job.

Shared by the jobs cancel, hold, release and requeue commands and by the me
dashboard, so both refuse the same jobs for the same reasons and neither
re-implements a check the other already has.

Each planner returns the argv to run and raises CommandError when the action has
to be refused. The CLI group turns that into its usual Error line, and the
dashboard shows it on its banner, so one wording serves both.
"""

import dataclasses
import os
import pwd
import re

from clustertool import process, slurm
from clustertool.process import CommandError

ACTIONS = ("cancel", "hold", "release", "requeue")

VERBS = {"cancel": "Cancel", "hold": "Hold", "release": "Release", "requeue": "Requeue"}
"""How each action names itself when refusing a job that is not the caller's."""

_FOLDED = re.compile(r"^(\d+)_\[(.*?)(?:%\d+)?\]$")
"""An array id squeue prints for elements that are still pending, like 123_[1-4].

The optional trailing %N is the concurrency limit Slurm prints inside the brackets,
which names no element.
"""


def named_elements(jobid: str) -> set[str]:
    """Return the element ids a folded array id names, or nothing for other forms."""
    folded = _FOLDED.match(jobid.strip())
    if not folded:
        return set()
    base, spec = folded.groups()
    named: set[str] = set()
    for part in spec.split(","):
        low, dash, high = part.partition("-")
        if dash and low.isdigit() and high.isdigit():
            named.update(f"{base}_{index}" for index in range(int(low), int(high) + 1))
        elif part.isdigit():
            named.add(f"{base}_{part}")
    return named


def checkable(jobid: str) -> str:
    """Return an id squeue -j will answer for, given one squeue printed.

    The two are not the same. While an array's elements are pending, squeue prints
    the whole range as 123_[1-4], and squeue -j does not match that form: it
    reports the job as absent and its owner as unknown. The base id answers in
    every case, and existence and ownership are properties of the array rather than
    of one element, so the base is what the checks ask about. The id the caller
    named is still what the action is run on, since scancel and scontrol do accept
    the folded form.
    """
    folded = _FOLDED.match(jobid.strip())
    return folded.group(1) if folded else jobid


@dataclasses.dataclass(frozen=True)
class Planned:
    """A checked action: what to run, what to say if it fails, and what it costs."""

    cmd: list[str]
    failure: str
    running: tuple[tuple[str, str], ...] = ()
    """The (jobid, elapsed) pairs whose work this action would discard."""


def caller() -> str:
    """Return the caller's username from the uid, never from the environment."""
    return pwd.getpwuid(os.getuid()).pw_name


def describe(jobid: str) -> tuple[str, str, str]:
    """Return (state, owner, elapsed) for a job, with empty fields when unknown."""
    code, out, _ = process.probe(
        ["squeue", "-t", "all", "-h", "-j", jobid, "-O", "State:32,UserName:64,TimeUsed:32"]
    )
    if code != 0:
        return "", "", ""
    row = next((line.split() for line in out.splitlines() if line.strip()), [])
    return tuple(row[:3]) if len(row) >= 3 else ("", "", "")


def refuse_foreign(owners: dict[str, str], verb: str) -> None:
    """Raise when any job is not the caller's, or when that cannot be established.

    A privileged user acting on a stranger's job is the case worth refusing: man
    scontrol records an admin-hold rather than a user-hold when they hold one, and
    its owner cannot lift that themselves.

    An owner that could not be read is refused too, rather than passed as though it
    were the caller's. Treating an empty answer as safe let the check stop applying
    for exactly the ids it could not resolve, while scancel and scontrol went on to
    act on them.
    """
    me = caller()
    unknown = sorted(jobid for jobid, owner in owners.items() if not owner)
    if unknown:
        raise CommandError(
            f"could not establish who owns {', '.join(unknown)}, so this was not run. "
            f"{verb} only jobs the controller still reports"
        )
    others = {jobid: owner for jobid, owner in owners.items() if owner != me}
    if not others:
        return
    listed = ", ".join(f"{jobid} ({owner})" for jobid, owner in sorted(others.items()))
    raise CommandError(f"these jobs belong to another user: {listed}. {verb} only your own")


def _in_queue(jobid: str) -> bool:
    """Return whether the controller holds anything the id names.

    A folded id is checked element by element rather than by its base. Checking the
    base alone accepted a range naming elements that do not exist, and scancel
    answers such a range by exiting cleanly having cancelled nothing, which is the
    outcome the refusal for an unknown id exists to prevent.
    """
    named = named_elements(jobid)
    if not named:
        return slurm.job_exists(checkable(jobid))
    return bool(named & slurm.array_elements(checkable(jobid)))


def plan(action: str, jobids: list[str]) -> Planned:
    """Check an action against Slurm and return what to run, or raise.

    The checks are the reason this is shared rather than duplicated: each one
    exists because Slurm's own behavior is not what a reader would guess, and a
    second copy would drift from the first.
    """
    if action not in ACTIONS:
        raise CommandError(f"unknown action {action!r}")
    if not jobids or any(not jobid.strip() for jobid in jobids):
        raise CommandError("a job id is required")
    listed = ", ".join(jobids)
    if action == "cancel":
        unknown = [jobid for jobid in jobids if not _in_queue(jobid)]
        if unknown:
            raise CommandError(
                f"not in the queue: {', '.join(unknown)}. The id may be mistyped, or "
                "the job may have already finished; scancel treats an unknown id as "
                "nothing to do, so this would have exited cleanly having canceled nothing"
            )
        refuse_foreign(
            {jobid: slurm.job_owner(checkable(jobid)) for jobid in jobids}, VERBS[action]
        )
        return Planned(["scancel", *jobids], "scancel failed")
    if action == "hold":
        refuse_foreign(
            {jobid: slurm.job_owner(checkable(jobid)) for jobid in jobids}, VERBS[action]
        )
        return Planned(
            ["scontrol", "hold", ",".join(jobids)],
            f"could not hold one or more of {listed}; see the messages above for which",
        )
    if action == "release":
        return Planned(
            ["scontrol", "release", ",".join(jobids)],
            f"could not release one or more of {listed}; see the messages above for which",
        )
    return _requeue(jobids, listed)


def _requeue(jobids: list[str], listed: str) -> Planned:
    """Plan a requeue, which needs the state as well as the owner.

    One squeue call answers both, and the elapsed time of a running job is what
    the caller has to be warned they are about to throw away.
    """
    described = {jobid: describe(checkable(jobid)) for jobid in jobids}
    missing = [jobid for jobid, (state, _, _) in described.items() if not state]
    if missing:
        raise CommandError(
            f"not in the queue: {', '.join(missing)}. The id may be mistyped, or the "
            "job may have finished and been dropped by the controller MinJobAge "
            "seconds later, in which case resubmit it rather than requeueing"
        )
    refuse_foreign({jobid: owner for jobid, (_, owner, _) in described.items()}, VERBS["requeue"])
    running = tuple(
        (jobid, elapsed) for jobid, (state, _, elapsed) in described.items() if state == "RUNNING"
    )
    return Planned(
        ["scontrol", "requeue", ",".join(jobids)],
        f"could not requeue one or more of {listed}. man scontrol requeues "
        "batch jobs only, and a job submitted with --no-requeue refuses; the messages "
        "above name which id failed",
        running=running,
    )
