"""Read-only helpers for querying Slurm."""

import re

from cluster_tools.process import CommandError
from cluster_tools.process import run as _run

BASE_PARTITIONS = ("kempner", "kempner_h100", "kempner_h200", "kempner_rtx")
REQUEUE_PARTITION = "kempner_requeue"
BASE_QOS = "kempner_base"
DEFAULT_CAP = 96

SlurmError = CommandError

_GPU_RE = re.compile(r"gres/gpu=(\d+)")
_INT_RE = re.compile(r"\d+")


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


def account_members(account: str) -> list[str]:
    """Return the sorted unique users in a fairshare account."""
    out = _run(["sshare", "-P", "--all", f"--account={account}"])
    members: set[str] = set()
    for line in out.splitlines()[1:]:
        parts = line.split("|")
        if len(parts) >= 2 and parts[1].strip():
            members.add(parts[1].strip())
    return sorted(members)


def priority_partitions() -> list[str]:
    """Return the live list of Kempner priority partitions."""
    out = _run(["scontrol", "show", "partition"])
    names = re.findall(r"PartitionName=(\S+)", out)
    return sorted(n for n in names if re.search(r"kempner.*priority", n, re.IGNORECASE))


def partition_nodes(partition: str) -> list[tuple[str, str]]:
    """Return (node, state) rows for a partition."""
    out = _run(["sinfo", "-h", "-N", "-p", partition, "-o", "%N %t"])
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        fields = line.split()
        if len(fields) >= 2:
            rows.append((fields[0], fields[1]))
    return rows


def node_info(node: str) -> dict:
    """Return the name, GPU count, and partitions for a node."""
    out = _run(["scontrol", "show", "node", node])
    if not out.strip() or "not found" in out.lower():
        raise CommandError(f"node '{node}' not found")
    name = re.search(r"NodeName=(\S+)", out)
    cfgtres = re.search(r"CfgTRES=(\S+)", out)
    partitions = re.search(r"Partitions=(\S+)", out)
    return {
        "name": name.group(1) if name else node,
        "gpus": parse_gpu_count(cfgtres.group(1)) if cfgtres else 0,
        "partitions": partitions.group(1).split(",") if partitions else [],
    }


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


_MEM_RE = re.compile(r"(?:^|,)mem=(\d+(?:\.\d+)?)([KMGT]?)")


def _tres_int(tres: str, key: str) -> int:
    """Return an integer TRES value, or 0 if absent."""
    match = re.search(rf"(?:^|,){re.escape(key)}=(\d+)", tres)
    return int(match.group(1)) if match else 0


def _tres_mem_gb(tres: str) -> float:
    """Return the memory TRES value in GB, or 0 if absent."""
    match = _MEM_RE.search(tres)
    if not match:
        return 0.0
    factors = {"K": 1 / 1024 / 1024, "M": 1 / 1024, "G": 1.0, "T": 1024.0, "": 1 / 1024}
    return float(match.group(1)) * factors[match.group(2)]


def node_free_resources(node: str) -> tuple[int, int, float]:
    """Return (free_gpu, free_cpu, free_mem_gb) for a node."""
    out = _run(["scontrol", "show", "node", node])
    cfg = re.search(r"CfgTRES=(\S+)", out)
    alloc = re.search(r"AllocTRES=(\S+)", out)
    cfg_tres = cfg.group(1) if cfg else ""
    alloc_tres = alloc.group(1) if alloc else ""
    free_mem = _tres_mem_gb(cfg_tres) - _tres_mem_gb(alloc_tres)
    return (
        parse_gpu_count(cfg_tres) - parse_gpu_count(alloc_tres),
        _tres_int(cfg_tres, "cpu") - _tres_int(alloc_tres, "cpu"),
        free_mem if free_mem > 0 else 0.0,
    )


def _field(text: str, key: str) -> str:
    """Return the value of a `key=value` field in scontrol output."""
    match = re.search(rf"(?:^|\s){re.escape(key)}=(\S*)", text)
    return match.group(1) if match else ""


def running_jobs_reqtres(partition: str) -> list[tuple[str, str, int, int, int]]:
    """Return (jobid, user, cpu, gpu, mem_mb) for running jobs in a partition."""
    out = _run(["scontrol", "show", "job", "-o"])
    jobs: list[tuple[str, str, int, int, int]] = []
    for line in out.splitlines():
        if "JobId=" not in line or _field(line, "JobState") != "RUNNING":
            continue
        if partition not in _field(line, "Partition").split(","):
            continue
        req = _field(line, "ReqTRES")
        user = _field(line, "UserId").split("(")[0]
        mem_mb = round(_tres_mem_gb(req) * 1024)
        jobs.append(
            (_field(line, "JobId"), user, _tres_int(req, "cpu"), parse_gpu_count(req), mem_mb)
        )
    return jobs


def partition_accounts(partition: str) -> list[str]:
    """Return the accounts allowed on a partition."""
    out = _run(["scontrol", "show", "partition", partition])
    match = re.search(r"AllowAccounts=(\S+)", out)
    if not match or match.group(1).upper() == "ALL":
        return []
    return match.group(1).split(",")


def user_fullnames(usernames: list[str]) -> dict[str, str]:
    """Return {username: full_name} (spaces as underscores) via one getent call."""
    if not usernames:
        return {}
    out = _run(["getent", "passwd", *usernames])
    names: dict[str, str] = {}
    for line in out.splitlines():
        fields = line.split(":")
        if len(fields) > 4:
            names[fields[0]] = fields[4].replace(" ", "_")
    return names
