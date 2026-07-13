"""Read-only helpers for querying Slurm about GPU usage."""

import re
import subprocess

BASE_PARTITIONS = ("kempner", "kempner_h100", "kempner_h200", "kempner_rtx")
REQUEUE_PARTITION = "kempner_requeue"
BASE_QOS = "kempner_base"
DEFAULT_CAP = 96

_GPU_RE = re.compile(r"gres/gpu=(\d+)")
_INT_RE = re.compile(r"\d+")


class SlurmError(RuntimeError):
    """Raised when a Slurm command is missing or cannot be run."""


def _run(cmd: list[str]) -> str:
    """Run a command and return its stdout."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise SlurmError(f"'{cmd[0]}' not found; are you on a Slurm login node?") from exc
    return result.stdout


def parse_gpu_count(text: str) -> int:
    """Return the GPU count encoded in a Slurm TRES string."""
    match = _GPU_RE.search(text)
    return int(match.group(1)) if match else 0


def account_cap() -> int:
    """Return the per-account base GPU cap from the base QoS."""
    out = _run(["sacctmgr", "-nP", "show", "qos", BASE_QOS, "format=MaxTRESPA"])
    gpus = parse_gpu_count(out)
    if gpus:
        return gpus
    match = _INT_RE.search(out)
    return int(match.group()) if match else DEFAULT_CAP


def account_exists(account: str) -> bool:
    """Return True if the Slurm account exists."""
    out = _run(["sacctmgr", "-nP", "show", "account", account, "format=Account"])
    return out.strip() == account


def priority_partitions() -> list[str]:
    """Return the live list of Kempner priority partitions."""
    out = _run(["scontrol", "show", "partition"])
    names = re.findall(r"PartitionName=(\S+)", out)
    return sorted(n for n in names if re.search(r"kempner.*priority", n, re.IGNORECASE))


def gpu_by_account(partitions: tuple[str, ...] | list[str]) -> dict[str, int]:
    """Return running GPU counts per account on the given partitions."""
    out = _run(
        [
            "squeue",
            "-h",
            "-t",
            "R",
            "-p",
            ",".join(partitions),
            "--Format=account:48,tres-alloc:512",
        ]
    )
    totals: dict[str, int] = {}
    for line in out.splitlines():
        fields = line.split()
        if not fields:
            continue
        gpus = parse_gpu_count(line)
        if gpus:
            totals[fields[0]] = totals.get(fields[0], 0) + gpus
    return totals


def gpu_rows(account: str, partitions: tuple[str, ...] | list[str]) -> list[tuple[str, str, int]]:
    """Return (user, partition, gpu_count) rows for an account's running jobs."""
    if not partitions:
        return []
    out = _run(
        [
            "squeue",
            "-h",
            "-t",
            "R",
            "-A",
            account,
            "-p",
            ",".join(partitions),
            "--Format=username:32,partition:30,tres-alloc:512",
        ]
    )
    rows: list[tuple[str, str, int]] = []
    for line in out.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        gpus = parse_gpu_count(line)
        if gpus:
            rows.append((fields[0], fields[1], gpus))
    return rows


def pending_at_cap(account: str, partitions: tuple[str, ...] | list[str]) -> int:
    """Return the number of jobs pending because the account hit the GPU cap."""
    if not partitions:
        return 0
    out = _run(
        [
            "squeue",
            "-h",
            "-t",
            "PD",
            "-A",
            account,
            "-p",
            ",".join(partitions),
            "-o",
            "%r",
        ]
    )
    return sum(1 for line in out.splitlines() if "MaxGRESPerAccount" in line)
