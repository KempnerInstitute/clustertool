"""Read-only helpers for querying Slurm."""

import re

from clustertool import process, site
from clustertool.process import CommandError
from clustertool.process import run as _run

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


def parse_gpu_count(text: str) -> int:
    """Return the GPU count encoded in a Slurm TRES string."""
    match = _GPU_RE.search(text)
    return int(match.group(1)) if match else 0


_GRES_GPU_RE = re.compile(r"gpu:(?:[^:()]+:)?(\d+)")


def _gres_gpus(text: str) -> int:
    """Return the total GPU count in a gres string like 'gpu:h100:4(S:0),gpu:mig:7(S:0)'.

    Sums every gpu entry, since a node can advertise more than one GPU type.
    """
    return sum(int(count) for count in _GRES_GPU_RE.findall(text or ""))


def gpus_allocated_in(partition: str) -> int:
    """Return the GPUs held by running jobs submitted to a partition.

    Reads each job's allocation rather than its request, so a job that asked with
    --gpus, or that Slurm gave a whole node, counts what it actually holds.
    """
    out = _run(["squeue", "-h", "-t", "R", "-p", partition, "-O", "tres-alloc:512"])
    return sum(parse_gpu_count(line) for line in out.splitlines())


def partition_gpu_util(
    partition: str, nodes: list[dict] | None = None
) -> tuple[int, int, int, int, int, float]:
    """Return (total, unavailable, used, other, free, percent) GPUs for a partition.

    Every GPU falls in exactly one column, so the four sum to total. Used is what
    jobs submitted to this partition hold and other is what jobs from partitions
    sharing the same nodes hold, wherever those nodes are. Of what is left,
    unavailable is idle on a node that cannot take a new job and free is idle on
    one that can. A drained node still running a job therefore contributes that
    job to used or other, not to unavailable. Percent is used over total. Pass
    nodes to reuse a node_capacity() result.
    """
    rows = [row for row in (nodes if nodes is not None else node_capacity()) if row["gpu_tot"]]
    rows = [row for row in rows if partition in row["partitions"]]
    total = sum(row["gpu_tot"] for row in rows)
    allocated = sum(row["gpu_tot"] - row["gpu_free"] for row in rows)
    free = sum(row["gpu_free"] for row in rows if row["available"])
    unavailable = sum(row["gpu_free"] for row in rows if not row["available"])
    used = min(gpus_allocated_in(partition), allocated)
    other = max(allocated - used, 0)
    percent = (100.0 * used / total) if total else 0.0
    return total, unavailable, used, other, free, percent


_RESUMABLE_STATES = frozenset({"DRAIN", "DRAINING", "DRAINED", "DOWN", "REBOOT", "INVALID_REG"})


def resumable_nodes(partition: str) -> list[tuple[str, str, str]]:
    """Return (name, state, reason) for the nodes in a partition that RESUME accepts.

    Per man scontrol, State=RESUME moves a node out of DRAIN, DRAINING, DOWN or
    REBOOT. The state is read from scontrol rather than sinfo's %T, which collapses
    a compound state such as DOWN+DRAIN+INVALID_REG to the single word inval and so
    hides a node that is exactly what the sweep is for. Matching is on the flag
    tokens, so a powered-down node is not swept by the substring in POWERED_DOWN.
    """
    result = []
    for line in _run(["scontrol", "show", "node", "-o"]).splitlines():
        kv = _node_kv(line)
        name = kv.get("NodeName")
        if not name or partition not in kv.get("Partitions", "").split(","):
            continue
        state = kv.get("State", "")
        flags = {flag.strip("*~#!%$@^-") for flag in state.upper().split("+")}
        if flags & _RESUMABLE_STATES:
            result.append((name, state, _node_reason(line)))
    return result


def _node_reason(line: str) -> str:
    """Return a node's Reason from one scontrol -o line.

    The reason runs to the end of the line and contains spaces, so it cannot be
    read as a whitespace-delimited key=value token.
    """
    match = re.search(r"Reason=(.*)$", line)
    if not match:
        return ""
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", match.group(1)).strip()


def resumable_nodes_by_name(names: tuple[str, ...]) -> dict[str, tuple[str, str, str]]:
    """Return {name: (name, state, reason)} for the named nodes, for those Slurm knows."""
    if not names:
        return {}
    out = _run(["sinfo", "-h", "-N", "-o", "%N|%T|%E", "-n", ",".join(names)])
    found = {}
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) == 3:
            found[parts[0].strip()] = (parts[0].strip(), parts[1].strip(), parts[2].strip())
    return found


def account_cap() -> int | None:
    """Return the per-account GPU cap from the base QoS, or None if there is none.

    Reads the gres/gpu entry of MaxTRESPA on the site's base QoS, falling back to
    the configured default cap when that entry is absent and the default is set.
    """
    out = _run(["sacctmgr", "-nP", "show", "qos", site.base_qos(), "format=MaxTRESPA"])
    gpus = parse_gpu_count(out)
    if gpus:
        return gpus
    configured = site.default_cap()
    return configured if configured > 0 else None


def account_exists(account: str) -> bool:
    """Return True if the Slurm account exists, matching the name case-insensitively.

    Raises if the query fails, so an unreachable accounting database is not
    reported as an account that does not exist.
    """
    cmd = ["sacctmgr", "-nP", "show", "account", account, "format=Account"]
    code, out, err = process.probe(cmd)
    if code != 0:
        raise CommandError(
            f"could not check whether account {account} exists: {err.strip() or code}"
        )
    names = {line.strip().lower() for line in out.splitlines() if line.strip()}
    return account.strip().lower() in names


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
    """Map a Slurm node state code to a status bucket.

    Per man sinfo the trailing flags carry meaning of their own: $ is a
    maintenance reservation and ~ is powered off, so neither can be stripped and
    bucketed by the base code alone.
    """
    if "$" in state:
        return "resv"
    if "~" in state or "%" in state or "!" in state:
        return "down"
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


def gpu_node_status() -> list[tuple[str, dict[str, int]]]:
    """Return [(gpu_type, {bucket: count})] for the site requeue partition.

    Each node is mapped to a GPU type from its features and a status bucket from
    its state. Types come back in a fixed order, omitting any with no nodes.
    """
    partition = site.requeue_partition()
    code, out, err = process.probe(["sinfo", "-h", "-N", "-p", partition, "-o", "%N|%t|%f"])
    if code != 0:
        raise CommandError(f"could not read partition {partition}: {err.strip() or code}")
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
    """Return (free_gpu, free_cpu, free_mem_mb) for a node.

    Free memory excludes MemSpecLimit, which is reserved for system use.
    """
    out = _run(["scontrol", "show", "node", node])
    cfg = re.search(r"CfgTRES=(\S+)", out)
    alloc = re.search(r"AllocTRES=(\S+)", out)
    cfg_tres = cfg.group(1) if cfg else ""
    alloc_tres = alloc.group(1) if alloc else ""
    reserved = _int_field(_field(out, "MemSpecLimit"))
    free_mem = _tres_mem_mb(cfg_tres) - reserved - _tres_mem_mb(alloc_tres)
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
    """Return the accounts allowed on a partition.

    Raises if the partition cannot be read, so a controller that is unreachable is
    not reported as a partition that allows every account.
    """
    code, out, err = process.probe(["scontrol", "-a", "show", "partition", partition])
    if code != 0:
        raise CommandError(
            f"could not read partition {partition}: {err.strip() or out.strip() or code}"
        )
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


def job_exists(jobid: str) -> bool:
    """Return True if Slurm knows the job id, queued or running.

    Raises when the controller could not be reached, so an outage is not reported
    as a job that does not exist. Only squeue's own 'Invalid job id' counts as an
    answer of no.
    """
    code, out, err = process.probe(["squeue", "-j", jobid, "-h", "-O", "jobid:32"])
    if code == 0:
        return True
    if "invalid job id" in (out + err).lower():
        return False
    raise CommandError(f"could not check job {jobid}: {err.strip() or out.strip() or code}")


def job_state_counts(user: str, pending_only: bool = False) -> dict[str, int]:
    """Return {state: count} for a user's queued and running jobs.

    Raises when the query fails, so a bulk cancel is never sized against a read
    that did not happen.
    """
    cmd = ["squeue", "-h", "-u", user, "-O", "state:32"]
    if pending_only:
        cmd += ["-t", "PENDING"]
    code, out, err = process.probe(cmd)
    if code != 0:
        raise CommandError(f"could not list {user}'s jobs: {err.strip() or code}")
    counts: dict[str, int] = {}
    for line in out.split():
        counts[line] = counts.get(line, 0) + 1
    return counts


def job_owner(jobid: str) -> str:
    """Return the user a job belongs to, or empty when Slurm does not know it."""
    code, out, _ = process.probe(["squeue", "-j", jobid, "-h", "-O", "username:64"])
    if code != 0:
        return ""
    return next((line.strip() for line in out.splitlines() if line.strip()), "")


def job_nodes(jobid: str) -> list[str]:
    """Return the expanded hostnames allocated to a job.

    An empty list means the job exists but holds no nodes yet, as a pending job
    does. A job Slurm does not know raises, so the two are not confused.
    """
    code, out, err = process.probe(["squeue", "-j", jobid, "-h", "-o", "%N"])
    if code != 0:
        raise CommandError(f"job '{jobid}' not found: {err.strip() or out.strip() or code}")
    compact = out.strip()
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
    """Return the accounting fields for a job (via sacct), or {} if none.

    A job array id matches every element, so the result also carries element_count
    and states, a count per final state. Reporting only the first row would let a
    array whose elements mostly failed read as the state of element zero.
    """
    code, out, err = process.probe(
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
    if code != 0:
        raise CommandError(f"could not read accounting for job {jobid}: {err.strip() or code}")
    rows = [row.split("|") for row in out.splitlines() if row.strip()]
    rows = [row for row in rows if len(row) >= 7]
    if not rows:
        return {}
    keys = ("state", "exit_code", "elapsed", "timelimit", "req_mem", "req_tres", "nodelist")
    info = dict(zip(keys, rows[0], strict=False))
    states: dict[str, int] = {}
    for row in rows:
        states[row[0]] = states.get(row[0], 0) + 1
    info["element_count"] = len(rows)
    info["states"] = states
    return info


def job_maxrss_mb(jobid: str) -> float:
    """Return the peak MaxRSS across a job's steps in MB (0 if unknown)."""
    out = _run(["sacct", "-j", jobid, "-n", "-P", "-o", "MaxRSS"])
    return max((_mem_to_mb(row.strip()) for row in out.splitlines()), default=0.0)


_UNRESOLVABLE_PATTERN = re.compile(r"%\d*[nNstS]")
_PADDED_PATTERN = re.compile(r"%(\d+)([AajJux])")


def _expand_log_pattern(path: str, fields: dict) -> str:
    """Expand the sbatch filename patterns sacct stores unexpanded.

    Returns an empty string when the pattern needs something only the running job
    knew, such as %N for the node it landed on: a half-expanded path names a file
    that cannot exist, which is worse than admitting the log cannot be located.
    man sbatch defines the symbols; %j is the job's own id, which for an array
    element is its JobIDRaw rather than the master's.
    """
    if _UNRESOLVABLE_PATTERN.search(path):
        return ""
    raw = fields.get("raw_id", "")
    master, _, task = fields.get("job_id", "").partition("_")
    values = {
        "%%": "%",
        "%A": master,
        "%a": task,
        "%J": raw,
        "%j": raw,
        "%u": fields.get("user", ""),
        "%x": fields.get("name", ""),
    }
    path = _PADDED_PATTERN.sub(
        lambda m: values.get(f"%{m.group(2)}", "").zfill(int(m.group(1))), path
    )
    for symbol, value in values.items():
        path = path.replace(symbol, value)
    return "" if "%" in path else path


def job_output_path(jobid: str) -> str:
    """Return a job's stdout path, or empty when it cannot be determined.

    Asks the controller first, which holds the expanded path while the job is
    recent, then accounting, which keeps the unexpanded pattern long after
    MinJobAge has purged the job from scontrol. A pattern sacct stores relative is
    relative to the job's WorkDir, not to the caller's directory.
    """
    code, out, _ = process.probe(["scontrol", "show", "job", jobid])
    if code == 0:
        match = re.search(r"StdOut=(\S+)", out)
        if match and match.group(1) not in ("", "(null)"):
            return match.group(1)

    code, out, _ = process.probe(
        [
            "sacct",
            "-j",
            jobid,
            "-X",
            "-n",
            "-P",
            "-o",
            "JobIDRaw,StdOut,WorkDir,JobName,User",
        ]
    )
    if code != 0:
        return ""
    row = next((line.split("|") for line in out.splitlines() if line.strip()), [])
    if len(row) < 5:
        return ""
    fields = {
        "raw_id": row[0].strip(),
        "job_id": jobid,
        "user": row[4].strip(),
        "name": row[3].strip(),
    }
    workdir = row[2].strip()
    stdout_path = _expand_log_pattern(row[1].strip(), fields) if row[1].strip() else ""
    if not stdout_path and workdir:
        stdout_path = f"slurm-{fields['raw_id'] or jobid}.out"
    if not stdout_path:
        return ""
    if not stdout_path.startswith("/"):
        if not workdir:
            return ""
        stdout_path = f"{workdir.rstrip('/')}/{stdout_path}"
    return stdout_path


def job_output_tail(jobid: str, lines: int = 200) -> str:
    """Return the tail of a job's stdout log, or empty if it cannot be read."""
    path = job_output_path(jobid)
    if not path:
        return ""
    code, out, _ = process.probe(["tail", "-n", str(lines), path])
    return out if code == 0 else ""


_BAD_NODE_STATES = (
    "DOWN",
    "DRAIN",
    "MAINT",
    "NOT_RESPONDING",
    "RESERVED",
    "COMPLETING",
    "FAIL",
    "POWER_DOWN",
    "POWERED_DOWN",
    "POWERING_DOWN",
    "INVAL",
)


def _node_kv(line: str) -> dict[str, str]:
    """Return the key=value tokens on one scontrol -o line."""
    return dict(token.split("=", 1) for token in line.split() if "=" in token)


def _int_field(value: str | None) -> int:
    """Return an integer field value, or 0 when absent or non-numeric."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def node_capacity() -> list[dict]:
    """Return free CPU/GPU/memory and partitions per node from one scontrol pass.

    Each row has name, partitions, state, available (False for a node that cannot
    take a new job), cpu_free, mem_free_mb, gpu_tot, and gpu_free. Free memory
    excludes MemSpecLimit, which slurm.conf reserves for system use and does not
    make available to jobs.
    """
    out = _run(["scontrol", "show", "node", "-o"])
    rows: list[dict] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        kv = _node_kv(line)
        name = kv.get("NodeName")
        if not name:
            continue
        state = kv.get("State", "")
        gpu_tot = parse_gpu_count(kv.get("CfgTRES", ""))
        gpu_alloc = parse_gpu_count(kv.get("AllocTRES", ""))
        rows.append(
            {
                "name": name,
                "partitions": [p for p in kv.get("Partitions", "").split(",") if p],
                "state": state,
                "available": not any(bad in state.upper() for bad in _BAD_NODE_STATES),
                "cpu_free": _int_field(kv.get("CPUTot")) - _int_field(kv.get("CPUAlloc")),
                "mem_free_mb": max(
                    0,
                    _int_field(kv.get("RealMemory"))
                    - _int_field(kv.get("MemSpecLimit"))
                    - _int_field(kv.get("AllocMem")),
                ),
                "gpu_tot": gpu_tot,
                "gpu_free": max(0, gpu_tot - gpu_alloc),
            }
        )
    return rows


def sacct_window_rows(
    fields: str,
    start: str,
    end: str,
    user: str | None = None,
    account: str | None = None,
    partition: str | None = None,
) -> list[list[str]]:
    """Return split sacct rows for a window, scoped by user, account, or partition.

    Raises if sacct fails, so a bad time string, an unknown user, or an
    unreachable slurmdbd is not reported as a window in which nothing ran.
    """
    cmd = ["sacct", "-X", "-n", "-P", "-o", fields, "-S", start, "-E", end]
    if account:
        cmd += ["-A", account, "-a"]
    elif partition:
        cmd += ["-r", partition, "-a"]
    elif user:
        cmd += ["-u", user]
    code, out, err = process.probe(cmd)
    if code != 0:
        raise CommandError(f"sacct failed: {err.strip() or out.strip() or code}")
    return [line.split("|") for line in out.splitlines() if line.strip()]


def percentile(sorted_values: list[int], pct: int) -> int | None:
    """Return the nearest-rank percentile of a pre-sorted list, or None if empty."""
    if not sorted_values:
        return None
    rank = max(1, (pct * len(sorted_values) + 99) // 100)
    return sorted_values[rank - 1]


def _float_field(value: str | None) -> float | None:
    """Return a float field value, or None when absent or non-numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _root_raw_usage() -> float:
    """Return the root account's RawUsage, the denominator for effective usage.

    sshare omits the root row when scoped with -A, so an account-scoped query has
    to ask for it separately or every ratio comes out zero.
    """
    code, out, _ = process.probe(
        ["sshare", "-a", "-P", "-o", "Account,User,RawUsage", "-A", "root"]
    )
    if code != 0:
        return 0.0
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) >= 3 and parts[0].strip() == "root" and not parts[1].strip():
            return _float_field(parts[2]) or 0.0
    return 0.0


def account_shares(account: str | None = None) -> list[dict]:
    """Return per-account normalized share and effective usage from sshare.

    Skips the header and per-user rows, keeping one row per account with
    norm_shares, effectv_usage, and raw_usage. Effective usage is computed from
    RawUsage against the root row rather than read from sshare's own
    EffectvUsage column, which is printed to six decimals and so rounds any
    account below a millionth of cluster usage to zero. Raises if the query
    fails, so an unreachable controller is not reported as a cluster with no
    accounts.
    """
    fields = "Account,User,RawShares,NormShares,RawUsage,EffectvUsage"
    cmd = ["sshare", "-a", "-P", "-o", fields]
    if account:
        cmd += ["-A", account]
    code, out, err = process.probe(cmd)
    if code != 0:
        raise CommandError(f"could not read fairshare from sshare: {err.strip() or code}")

    parsed = []
    root_usage = 0.0
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) < 6:
            continue
        name, user = parts[0].strip(), parts[1].strip()
        if name == "Account" or user:
            continue
        raw_usage = _float_field(parts[4]) or 0.0
        if name == "root":
            root_usage = raw_usage
            continue
        parsed.append((name, _float_field(parts[3]), raw_usage))
    if not root_usage:
        root_usage = _root_raw_usage()

    rows: list[dict] = []
    for name, norm_shares, raw_usage in parsed:
        rows.append(
            {
                "account": name,
                "norm_shares": norm_shares,
                "raw_usage": raw_usage,
                "effectv_usage": (raw_usage / root_usage) if root_usage else 0.0,
            }
        )
    return rows


def user_associations(user: str) -> list[tuple[str, str, str]]:
    """Return the unique (account, partition, qos) associations a user may submit under."""
    cmd = ["sacctmgr", "-n", "-P", "show", "assoc", f"user={user}", "format=Account,Partition,QOS"]
    rows: list[tuple[str, str, str]] = []
    seen = set()
    for line in _run(cmd).splitlines():
        parts = line.split("|")
        if len(parts) != 3 or not parts[0]:
            continue
        key = (parts[0], parts[1], parts[2])
        if key not in seen:
            seen.add(key)
            rows.append(key)
    return rows


def default_account(user: str) -> str:
    """Return a user's default Slurm account, or '' when unknown."""
    lines = _run(
        ["sacctmgr", "-n", "-P", "show", "user", user, "format=DefaultAccount"]
    ).splitlines()
    return lines[0].strip() if lines and lines[0].strip() else ""
