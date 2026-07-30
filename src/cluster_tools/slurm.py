"""Read-only helpers for querying Slurm."""

import re

from cluster_tools import site
from cluster_tools.process import CommandError
from cluster_tools.process import run as _run

GPU_STATUS_BUCKETS = ("idle", "mixed", "alloc", "resv", "drain", "down")

_SITE_CONSTANTS = {
    "BASE_PARTITIONS": "base_partitions",
    "REQUEUE_PARTITION": "requeue_partition",
    "BASE_QOS": "base_qos",
    "DEFAULT_CAP": "default_cap",
    "PARTITION_LIMITS": "partition_limits",
    "GPU_TYPE_PARTITION": "gpu_type_partition",
}


def __getattr__(name: str):
    """Serve site-derived constants dynamically from the active configuration."""
    accessor = _SITE_CONSTANTS.get(name)
    if accessor is not None:
        return getattr(site, accessor)()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


SlurmError = CommandError

_GPU_RE = re.compile(r"gres/gpu=(\d+)")
_INT_RE = re.compile(r"\d+")


def parse_gpu_count(text: str) -> int:
    """Return the GPU count encoded in a Slurm TRES string."""
    match = _GPU_RE.search(text)
    return int(match.group(1)) if match else 0


_GRES_GPU_RE = re.compile(r"gpu:(?:[^:()]+:)?(\d+)")


def _gres_gpus(text: str) -> int:
    """Return the GPU count in a gres string like 'gpu:h100:4(...)' or 'gres/gpu:1'."""
    match = _GRES_GPU_RE.search(text or "")
    return int(match.group(1)) if match else 0


def _sum_node_gpus(extra: list[str]) -> int:
    total = 0
    for line in _run(["sinfo", "-h", "-N", "-o", "%N %G", *extra]).splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            total += _gres_gpus(parts[1])
    return total


def partition_gpu_util(partition: str) -> tuple[int, int, int, int, float]:
    """Return (total, down, available, used, percent) GPUs for a partition.

    Available excludes GPUs on down or drained nodes; percent is used/available.
    """
    total = _sum_node_gpus(["-p", partition])
    down = _sum_node_gpus(["-R", "-p", partition])
    available = max(total - down, 0)
    used = 0
    for line in _run(["squeue", "-h", "-t", "R", "-o", "%D %b", "-p", partition]).splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit():
            used += int(parts[0]) * _gres_gpus(parts[1])
    percent = (100.0 * used / available) if available else 0.0
    return total, down, available, used, percent


def drained_nodes(partition: str) -> list[str]:
    """Return the names of drained or draining nodes in a partition."""
    result = []
    for line in _run(["sinfo", "-h", "-N", "-o", "%N %T", "-p", partition]).splitlines():
        parts = line.split()
        if len(parts) == 2 and "drain" in parts[1].lower():
            result.append(parts[0])
    return result


def account_cap() -> int:
    """Return the per-account base GPU cap from the base QoS."""
    out = _run(["sacctmgr", "-nP", "show", "qos", site.base_qos(), "format=MaxTRESPA"])
    gpus = parse_gpu_count(out)
    if gpus:
        return gpus
    match = _INT_RE.search(out)
    return int(match.group()) if match else site.default_cap()


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
    """Return the live list of priority partitions matching the site pattern."""
    out = _run(["scontrol", "show", "partition"])
    names = re.findall(r"PartitionName=(\S+)", out)
    pattern = site.priority_pattern()
    return sorted(n for n in names if re.search(pattern, n, re.IGNORECASE))


def partition_nodes(partition: str) -> list[tuple[str, str]]:
    """Return (node, state) rows for a partition."""
    out = _run(["sinfo", "-h", "-N", "-p", partition, "-o", "%N %t"])
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        fields = line.split()
        if len(fields) >= 2:
            rows.append((fields[0], fields[1]))
    return rows


def _gpu_type_from_features(features: str) -> str:
    """Return the GPU type label for a node from its Slurm features."""
    tags = {tag.strip().lower() for tag in features.split(",")}
    for label, tag in site.gpu_status_types():
        if tag in tags:
            return label
    return "Other"


def _status_bucket(state: str) -> str:
    """Map a Slurm node state code (flags stripped) to a status bucket."""
    match = re.match(r"[a-z]+", state.lower())
    base = match.group() if match else ""
    if base.startswith(("idle", "plnd", "plan")):
        return "idle"
    if base.startswith("mix"):
        return "mixed"
    if base.startswith(("alloc", "comp")):
        return "alloc"
    if base.startswith(("resv", "rese", "maint")):
        return "resv"
    if base.startswith("dr"):
        return "drain"
    return "down"


def kempner_gpu_node_status() -> list[tuple[str, dict[str, int]]]:
    """Return [(gpu_type, {bucket: count})] for kempner_requeue nodes.

    Each node in the requeue partition (which spans every Kempner GPU node) is
    mapped to a GPU type from its features and a status bucket from its state.
    Types come back in a fixed order, omitting any with no nodes.
    """
    out = _run(["sinfo", "-h", "-N", "-p", site.requeue_partition(), "-o", "%N|%t|%f"])
    counts: dict[str, dict[str, int]] = {}
    seen: set[str] = set()
    for line in out.splitlines():
        fields = line.split("|")
        if len(fields) < 3 or fields[0] in seen:
            continue
        seen.add(fields[0])
        gtype = _gpu_type_from_features(fields[2])
        counts.setdefault(gtype, dict.fromkeys(GPU_STATUS_BUCKETS, 0))
        counts[gtype][_status_bucket(fields[1])] += 1
    order = [label for label, _ in site.gpu_status_types()] + ["Other"]
    return [(gtype, counts[gtype]) for gtype in order if gtype in counts]


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


def _tres_mem_mb(tres: str) -> float:
    """Return the memory TRES value in MB, or 0 if absent."""
    match = _MEM_RE.search(tres)
    if not match:
        return 0.0
    factors = {"K": 1 / 1024, "M": 1.0, "G": 1024.0, "T": 1024.0 * 1024, "": 1.0}
    return float(match.group(1)) * factors[match.group(2)]


def node_free_resources(node: str) -> tuple[int, int, float]:
    """Return (free_gpu, free_cpu, free_mem_mb) for a node."""
    out = _run(["scontrol", "show", "node", node])
    cfg = re.search(r"CfgTRES=(\S+)", out)
    alloc = re.search(r"AllocTRES=(\S+)", out)
    cfg_tres = cfg.group(1) if cfg else ""
    alloc_tres = alloc.group(1) if alloc else ""
    free_mem = _tres_mem_mb(cfg_tres) - _tres_mem_mb(alloc_tres)
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
        mem_mb = round(_tres_mem_mb(req))
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


def job_nodes(jobid: str) -> list[str]:
    """Return the expanded hostnames allocated to a job."""
    compact = _run(["squeue", "-j", jobid, "-h", "-o", "%N"]).strip()
    if not compact:
        return []
    return [host for host in _run(["scontrol", "show", "hostnames", compact]).split() if host]


def first_hostname() -> str:
    """Return the first hostname in the current job's node list."""
    hosts = _run(["scontrol", "show", "hostnames"]).split()
    return hosts[0] if hosts else ""


def my_jobs(user: str) -> list[tuple[str, str, str, str, str]]:
    """Return (jobid, state, partition, elapsed, reason) rows for a user's jobs."""
    out = _run(["squeue", "-h", "-u", user, "-o", "%i|%T|%P|%M|%r"])
    rows: list[tuple[str, str, str, str, str]] = []
    for line in out.splitlines():
        fields = line.split("|")
        if len(fields) >= 5:
            rows.append((fields[0], fields[1], fields[2], fields[3], fields[4]))
    return rows


def user_fairshare(user: str) -> list[tuple[str, str]]:
    """Return (account, fairshare_score) rows for the accounts a user belongs to."""
    out = _run(["sshare", "-h", "-P", "-U", "-u", user, "-o", "Account,FairShare"])
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        fields = line.split("|")
        if len(fields) >= 2 and fields[0].strip():
            rows.append((fields[0].strip(), fields[1].strip()))
    return rows


def user_gpu_count(user: str) -> int:
    """Return the number of GPUs a user has allocated to running jobs."""
    out = _run(["squeue", "-h", "-t", "R", "-u", user, "-O", "tres-alloc:512"])
    return sum(parse_gpu_count(line) for line in out.splitlines())


def _mem_to_mb(value: str) -> float:
    """Convert a Slurm memory string like '61.2G' or '2136K' to MB (0 if empty)."""
    match = re.match(r"([\d.]+)([KMGT]?)", value)
    if not match:
        return 0.0
    factors = {"K": 1 / 1024, "M": 1.0, "G": 1024.0, "T": 1024.0 * 1024, "": 1.0}
    return float(match.group(1)) * factors[match.group(2)]


def job_accounting(jobid: str) -> dict:
    """Return the accounting fields for a finished job (via sacct), or {} if none."""
    out = _run(
        [
            "sacct",
            "-j",
            jobid,
            "-X",
            "-n",
            "-P",
            "-o",
            "State,ExitCode,Elapsed,Timelimit,ReqMem,ReqTRES,NodeList",
        ]
    )
    line = next((row for row in out.splitlines() if row.strip()), "")
    fields = line.split("|")
    if len(fields) < 7:
        return {}
    keys = ("state", "exit_code", "elapsed", "timelimit", "req_mem", "req_tres", "nodelist")
    return dict(zip(keys, fields, strict=False))


def job_maxrss_mb(jobid: str) -> float:
    """Return the peak MaxRSS across a job's steps in MB (0 if unknown)."""
    out = _run(["sacct", "-j", jobid, "-n", "-P", "-o", "MaxRSS"])
    return max((_mem_to_mb(row.strip()) for row in out.splitlines()), default=0.0)


def job_output_tail(jobid: str, lines: int = 200) -> str:
    """Return the tail of a job's stdout log, or empty if it cannot be read."""
    try:
        out = _run(["scontrol", "show", "job", jobid])
    except CommandError:
        return ""
    match = re.search(r"StdOut=(\S+)", out)
    if not match or match.group(1) in ("", "(null)"):
        return ""
    try:
        return _run(["tail", "-n", str(lines), match.group(1)])
    except CommandError:
        return ""
