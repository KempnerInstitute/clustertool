"""jobs debug command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords

_STATE_RULES = [
    ("OUT_OF_MEMORY", "Ran out of memory", "Request more memory (--mem) or reduce memory usage."),
    ("TIMEOUT", "Hit the time limit", "Increase --time, or checkpoint and resume."),
    ("NODE_FAIL", "A node failed", "Resubmit; add a requeue-on-failure directive for resilience."),
    ("CANCELLED", "Canceled", "Canceled by you or an admin (scancel, or a QoS or time limit)."),
    ("PREEMPTED", "Preempted", "A higher-priority job took the nodes; resubmit."),
    ("DEADLINE", "Hit the deadline", "The job passed its --deadline before starting."),
    ("BOOT_FAIL", "A node failed to boot", "Resubmit, and report the node if it recurs."),
]

_MAX_SIGNAL = 64

_LOG_RULES = [
    (
        "CUDA out of memory",
        "GPU ran out of memory (CUDA)",
        "Reduce batch or model size, or use more GPUs.",
    ),
    (
        "ModuleNotFoundError",
        "A Python module was missing",
        "Check your environment and module loads.",
    ),
    ("ImportError", "A Python import failed", "Check your environment and installed packages."),
    ("command not found", "A command was not found", "Check your PATH and module loads."),
    (
        "No space left on device",
        "A filesystem was full",
        "Check quotas with clustertool storage quota.",
    ),
    ("Permission denied", "Permission was denied", "Check file and directory permissions."),
    (
        "Traceback (most recent call last)",
        "A Python exception was raised",
        "See the log for the traceback.",
    ),
]


def _diagnose(info: dict, log_text: str) -> list[tuple[str, str]]:
    """Return [(cause, suggestion)] findings for a finished job."""
    findings: list[tuple[str, str]] = []
    state = info.get("state", "")
    for key, cause, suggestion in _STATE_RULES:
        if state.startswith(key):
            findings.append((cause, suggestion))
    code, _, signal = info.get("exit_code", "").partition(":")
    matched_state = any(state.startswith(key) for key, _, _ in _STATE_RULES)
    signal_num = int(signal) if signal.isdigit() else 0
    if signal == "9" and not matched_state:
        findings.append(
            ("Killed by signal 9 (SIGKILL)", "Often an out-of-memory kill; request more memory.")
        )
    elif signal_num and signal_num <= _MAX_SIGNAL and not matched_state:
        findings.append(
            (f"Killed by signal {signal}", "The job was terminated by a signal; check the log.")
        )
    if code and code != "0" and not matched_state:
        findings.append(
            (f"Exited with non-zero code {code}", "Check the log with 'jobs log JOBID'.")
        )
    for pattern, cause, suggestion in _LOG_RULES:
        if pattern in log_text:
            findings.append((cause, suggestion))
    if not findings and state == "COMPLETED":
        findings.append(("Completed successfully", "For efficiency, see clustertool jobs scope."))
    return findings


@keywords("diagnose", "failed", "postmortem", "oom", "crash", "error", "died")
@click.command("debug")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
def debug(jobid: str) -> None:
    """Explain why a finished job failed, from its accounting and log (via sacct).

    Reads the job's final state, exit code, time, and memory, scans the tail of
    its stdout for common error patterns, and prints a plain-English diagnosis
    with suggestions. Best for finished jobs; a running job may lack final data.
    For a job that has not started yet, use 'jobs why' instead.

    \b
    Use cases:
      - Understand why a job died: out of memory, timeout, node failure, or a code error.
      - Get a suggested fix without decoding Slurm and CUDA messages by hand.

    \b
    Inputs:
      JOBID  A Slurm job id.
    """
    info = slurm.job_accounting(jobid)
    if not info:
        raise click.ClickException(
            f"no accounting record for job {jobid}: it may not exist, or may belong to another user"
        )
    elements = info.get("element_count", 1)
    if elements > 1:
        click.echo(f"Job {jobid} is an array of {elements} elements:")
        for state, count in sorted(info["states"].items(), key=lambda kv: -kv[1]):
            click.echo(f"  {count:>6}  {state}")
        click.echo("")
        click.echo(f"Name one to diagnose it, for example '{jobid}_0'.")
        return
    if info["state"].startswith("PENDING"):
        click.echo(f"Job {jobid} has not started ({info['state']}).")
        click.echo(f"There is nothing to diagnose yet; 'jobs why {jobid}' explains the wait.")
        return

    maxrss_mb = slurm.job_maxrss_mb(jobid)
    log_text = slurm.job_output_tail(jobid)
    findings = _diagnose(info, log_text)

    click.echo(f"Job {jobid} diagnosis")
    click.echo("")
    click.echo(f"State:    {info['state']} (exit {info['exit_code']})")
    click.echo(f"Elapsed:  {info['elapsed']} / {info['timelimit']}")
    click.echo(f"Memory:   peak {maxrss_mb:.0f} MB used, {info['req_mem']} requested")
    if info.get("nodelist"):
        click.echo(f"Nodes:    {info['nodelist']}")
    click.echo("")
    if findings:
        click.echo("Diagnosis:")
        for cause, suggestion in findings:
            click.echo(f"  - {cause}")
            click.echo(f"      {suggestion}")
    else:
        click.echo("No specific cause detected. Check the log, jobs show, and jobs stats.")
