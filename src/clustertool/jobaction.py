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

from clustertool import process, slurm
from clustertool.process import CommandError

ACTIONS = ("cancel", "hold", "release", "requeue")

VERBS = {"cancel": "Cancel", "hold": "Hold", "release": "Release", "requeue": "Requeue"}
"""How each action names itself when refusing a job that is not the caller's."""


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
    """Raise when any job belongs to someone other than the caller.

    A privileged user acting on a stranger's job is the case worth refusing: man
    scontrol records an admin-hold rather than a user-hold when they hold one, and
    its owner cannot lift that themselves.
    """
    me = caller()
    others = {jobid: owner for jobid, owner in owners.items() if owner and owner != me}
    if not others:
        return
    listed = ", ".join(f"{jobid} ({owner})" for jobid, owner in sorted(others.items()))
    raise CommandError(f"these jobs belong to another user: {listed}. {verb} only your own")


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
        unknown = [jobid for jobid in jobids if not slurm.job_exists(jobid)]
        if unknown:
            raise CommandError(
                f"not in the queue: {', '.join(unknown)}. The id may be mistyped, or "
                "the job may have already finished; scancel treats an unknown id as "
                "nothing to do, so this would have exited cleanly having canceled nothing"
            )
        refuse_foreign({jobid: slurm.job_owner(jobid) for jobid in jobids}, VERBS[action])
        return Planned(["scancel", *jobids], "scancel failed")
    if action == "hold":
        refuse_foreign({jobid: slurm.job_owner(jobid) for jobid in jobids}, VERBS[action])
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
    described = {jobid: describe(jobid) for jobid in jobids}
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
