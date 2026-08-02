"""Read-only helpers for querying Slurm."""

import pwd
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


RESUMABLE_STATES = frozenset({"DRAIN", "DOWN", "REBOOT_REQUESTED", "REBOOT_ISSUED", "INVALID_REG"})
"""The flags scontrol prints that State=RESUME accepts.

man scontrol names REBOOT, but Slurm only ever prints REBOOT_REQUESTED or
REBOOT_ISSUED, so a bare REBOOT would match nothing. DRAINED and DRAINING are
sinfo's spellings; scontrol prints the DRAIN flag.
"""


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
        if flags & RESUMABLE_STATES:
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
    """Return {name: (name, state, reason)} for the named nodes Slurm knows.

    Reads scontrol for the same reason the sweep does, so both paths report the
    same compound state rather than sinfo's collapsed %T. A name may be a
    hostlist expression such as node[1-4], which scontrol expands, so the keys
    are the nodes that were actually matched and not the string typed.
    """
    if not names:
        return {}
    code, out, err = process.probe(["scontrol", "show", "node", "-o", ",".join(names)])
    if code != 0:
        if "not found" in (out + err).lower() or "invalid" in (out + err).lower():
            return {}
        raise CommandError(f"could not read the named nodes: {err.strip() or code}")
    found = {}
    for line in out.splitlines():
        kv = _node_kv(line)
        name = kv.get("NodeName")
        if name:
            found[name] = (name, kv.get("State", ""), _node_reason(line))
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


def partition_exists(partition: str) -> bool:
    """Return True if the cluster has this partition, even with no nodes in it.

    -a is passed because man scontrol scopes it to partitions that are hidden or
    unavailable to the caller's group, and without it a partition the caller
    cannot submit to is reported as one that does not exist. Raises if the query
    fails, so an unreachable controller is not reported the same way either.
    """
    code, out, err = process.probe(["scontrol", "-a", "show", "partition", partition])
    if code == 0:
        return True
    if "not found" in (out + err).lower():
        return False
    detail = err.strip() or out.strip() or code
    raise CommandError(f"could not check whether partition {partition} exists: {detail}")


def canonical_account(account: str) -> str | None:
    """Return an account's name as slurmdbd spells it, or None if it does not exist.

    Slurm matches an account name without regard to case, but a site tool keyed on
    the string it was handed will not find the rows sacct returns under the
    canonical spelling, so the caller passes on what the database holds.
    """
    code, out, err = process.probe(
        ["sacctmgr", "-n", "-P", "show", "account", f"name={account}", "format=Account"]
    )
    if code != 0:
        raise CommandError(
            f"could not check whether account {account} exists: {err.strip() or code}"
        )
    for line in out.splitlines():
        name = line.strip()
        if name:
            return name
    return None


def user_exists(user: str) -> bool:
    """Return True if the name resolves to an account on this host.

    squeue answers a name that does not resolve with an error on stderr and an
    empty list while still exiting 0, so the name has to be checked here. A
    numeric uid needs no passwd entry for squeue to accept it, and is treated the
    same way only when it does resolve.
    """
    try:
        if user.isdigit():
            pwd.getpwuid(int(user))
        else:
            pwd.getpwnam(user)
    except (KeyError, OverflowError, ValueError):
        return False
    return True


def account_members(account: str) -> list[str]:
    """Return the sorted unique users in a fairshare account.

    Raises if sshare fails, since an empty list reads as an account with no
    members: sshare exits nonzero when the multifactor plugin is absent or the
    controller is unreachable, and neither is an empty account.
    """
    code, out, err = process.probe(["sshare", "-P", "--all", f"--account={account}"])
    if code != 0:
        raise CommandError(f"could not list the members of {account}: {err.strip() or code}")
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
    """Return (node, state) rows for a partition.

    Raises if sinfo fails, since callers read an empty result as a partition that
    does not exist, and an unreachable controller is not the user's typo.

    sinfo refuses -a together with -p, so a partition the caller's group cannot
    use comes back empty rather than hidden. The caller distinguishes that from a
    mistyped name by asking whether the partition exists.

    -p takes a comma-separated list and -N prints one row per node and partition,
    so a node in two of the named partitions appears twice. Each node is returned
    once, with the state of its first row, since a node has one state.
    """
    code, out, err = process.probe(["sinfo", "-h", "-N", "-p", partition, "-o", "%N %t"])
    if code != 0:
        raise CommandError(f"could not list the nodes in {partition}: {err.strip() or code}")
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in out.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] not in seen:
            seen.add(fields[0])
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
    bucketed by the base code alone. A node marked * is not responding and, in
    man sinfo's words, "will not be allocated any new work", so a base state that
    would otherwise read as available becomes down. A node already drained,
    reserved or down keeps its more specific bucket, which says the same thing
    about availability while naming the reason.
    """
    if "$" in state:
        return "resv"
    if "~" in state or "%" in state or "!" in state:
        return "down"
    match = re.match(r"[a-z]+", state.lower())
    base = match.group() if match else ""
    if base.startswith(("idle", "plnd", "plan")):
        bucket = "idle"
    elif base.startswith("mix"):
        bucket = "mixed"
    elif base.startswith(("alloc", "comp")):
        bucket = "alloc"
    elif base.startswith(("resv", "rese", "maint")):
        bucket = "resv"
    elif base.startswith("dr"):
        bucket = "drain"
    else:
        bucket = "down"
    if "*" in state and bucket in ("idle", "mixed", "alloc"):
        return "down"
    return bucket


def _has_gpu_gres(gres: str) -> bool:
    """Return True if a sinfo %G field names a gpu resource.

    sinfo writes the configured gres as name:type:count, and prints the literal
    (null) for a node with none, which is not the TRES syntax parse_gpu_count
    reads.
    """
    return any(part.strip().startswith("gpu:") for part in gres.split(","))


def gpu_node_status() -> list[tuple[str, dict[str, int]]]:
    """Return [(gpu_type, {bucket: count})] for the site requeue partition.

    Each node is mapped to a GPU type from its features and a status bucket from
    its state. Types come back in a fixed order, omitting any with no nodes.

    A node with no GPU is skipped. The requeue partition is configured, not
    guaranteed to be GPU-only, and a site that points it at a partition spanning
    the whole cluster would otherwise get every CPU node counted here.
    """
    partition = site.requeue_partition()
    code, out, err = process.probe(["sinfo", "-h", "-N", "-p", partition, "-o", "%N|%t|%f|%G"])
    if code != 0:
        raise CommandError(f"could not read partition {partition}: {err.strip() or code}")
    counts: dict[str, dict[str, int]] = {}
    seen: set[str] = set()
    for line in out.splitlines():
        fields = line.split("|")
        if len(fields) < 4 or fields[0] in seen:
            continue
        if not _has_gpu_gres(fields[3]):
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
    return sum(1 for line in out.splitlines() if line.strip().startswith("QOSMaxGRESPerAccount"))


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


def _field(text: str, key: str) -> str:
    """Return the value of a `key=value` field in scontrol output."""
    match = re.search(rf"(?:^|\s){re.escape(key)}=(\S*)", text)
    return match.group(1) if match else ""


def running_jobs_alloctres(partition: str) -> list[tuple[str, str, int, int, int]]:
    """Return (jobid, user, cpu, gpu, mem_mb) for running jobs in a partition.

    AllocTRES is what the job holds; ReqTRES is what it asked for. They differ
    whenever Slurm rounds a request up to a whole node or a whole socket, which
    is exactly the case a per-GPU norm exists to catch, so reading the request
    both understated the job and hid the jobs holding the most.

    The array element id is reported rather than the raw job id, since the raw id
    of element 1 can be the array's own id and would send a follow-up query to
    the whole array.
    """
    out = _run(["scontrol", "-a", "show", "job", "-o"])
    jobs: list[tuple[str, str, int, int, int]] = []
    for line in out.splitlines():
        if "JobId=" not in line or _field(line, "JobState") != "RUNNING":
            continue
        if partition not in _field(line, "Partition").split(","):
            continue
        alloc = _field(line, "AllocTRES")
        user = _field(line, "UserId").split("(")[0]
        mem_mb = round(_tres_mem_mb(alloc))
        array_job = _field(line, "ArrayJobId")
        array_task = _field(line, "ArrayTaskId")
        jobid = f"{array_job}_{array_task}" if array_job and array_task else _field(line, "JobId")
        jobs.append((jobid, user, _tres_int(alloc, "cpu"), parse_gpu_count(alloc), mem_mb))
    return jobs


def partition_max_gpus(partition: str) -> int:
    """Return the most GPUs any one node in a partition has, or 0 when unknown.

    A request above that can never be satisfied, and sbatch reports it only as
    "Requested node configuration is not available".
    """
    try:
        rows = node_capacity()
    except CommandError:
        return 0
    return max((row["gpu_tot"] for row in rows if partition in row["partitions"]), default=0)


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
    as a job that does not exist. squeue answers a job id whose array element does
    not exist with exit 0 and no rows, so an empty answer counts as no just as its
    own 'Invalid job id' does. -t all is passed because squeue otherwise omits a
    suspended job, which scancel does act on.
    """
    code, out, err = process.probe(["squeue", "-t", "all", "-j", jobid, "-h", "-O", "jobid:32"])
    if code == 0:
        return bool(out.strip())
    if "invalid job id" in (out + err).lower():
        return False
    raise CommandError(f"could not check job {jobid}: {err.strip() or out.strip() or code}")


def job_state_counts(user: str, pending_only: bool = False) -> dict[str, int]:
    """Return {state: count} for a user's jobs that scancel would act on.

    Raises when the query fails, so a bulk cancel is never sized against a read
    that did not happen. -r counts each array element, since squeue otherwise
    folds a pending array onto one line while scancel acts on every element. The
    states are the three man scancel names, so the count is what would be killed.
    """
    cmd = ["squeue", "-h", "-r", "-u", user, "-O", "state:32"]
    cmd += ["-t", "PENDING"] if pending_only else ["-t", "PENDING,RUNNING,SUSPENDED"]
    code, out, err = process.probe(cmd)
    if code != 0:
        raise CommandError(f"could not list {user}'s jobs: {err.strip() or code}")
    counts: dict[str, int] = {}
    for line in out.split():
        counts[line] = counts.get(line, 0) + 1
    return counts


def job_owner(jobid: str) -> str:
    """Return the user a job belongs to, or empty when Slurm has no record of it.

    Raises when the query fails, because callers use this to refuse acting on
    someone else's job: an unknown owner must not read as "not theirs". -t all is
    passed for the same reason job_exists passes it, since squeue otherwise omits
    a suspended job, which scancel and scontrol both still act on.
    """
    if "," in jobid:
        raise CommandError(
            f"'{jobid}' names more than one job. squeue answers a list in its own sort "
            "order, so only one of the owners would be checked. Give a single job id"
        )
    code, out, err = process.probe(["squeue", "-t", "all", "-j", jobid, "-h", "-O", "username:64"])
    if code != 0:
        if "invalid job id" in (out + err).lower():
            return ""
        raise CommandError(f"could not check who owns job {jobid}: {err.strip() or code}")
    owners = {line.strip() for line in out.splitlines() if line.strip()}
    if len(owners) > 1:
        raise CommandError(f"job {jobid} reports more than one owner: {', '.join(sorted(owners))}")
    return owners.pop() if owners else ""


def job_nodes(jobid: str) -> list[str]:
    """Return the expanded hostnames allocated to a job.

    An empty list means the job exists but holds no nodes yet, as a pending job
    does. A job Slurm does not know raises, so the two are not confused. -t all
    is passed for the reason job_owner passes it: a suspended job still holds its
    nodes, and squeue's default states would report it as holding none.
    """
    code, out, err = process.probe(["squeue", "-t", "all", "-j", jobid, "-h", "-o", "%N"])
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
    array whose elements mostly failed read as the state of element zero. --array
    is passed because sacct otherwise folds a contiguous pending range onto one
    row, which would count a hundred waiting elements as one.
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
            "JobID,State,ExitCode,Elapsed,Timelimit,ReqMem,ReqTRES,NodeList",
            "--array",
        ]
    )
    if code != 0:
        raise CommandError(f"could not read accounting for job {jobid}: {err.strip() or code}")
    rows = [row.split("|") for row in out.splitlines() if row.strip()]
    rows = [row for row in rows if len(row) >= 8]
    if not rows:
        return {}
    keys = ("state", "exit_code", "elapsed", "timelimit", "req_mem", "req_tres", "nodelist")
    info = dict(zip(keys, rows[0][1:], strict=False))
    states: dict[str, int] = {}
    for row in rows:
        states[row[1]] = states.get(row[1], 0) + 1
    info["element_count"] = len(rows)
    info["states"] = states
    info["first_element"] = rows[0][0].strip()
    return info


def job_memory_mb(jobid: str) -> tuple[float | None, float | None, int]:
    """Return (peak per-task MiB, total across tasks MiB, task count) for a job.

    man sacct defines MaxRSS as the highest watermark of any one task, while
    ReqMem is the whole allocation's request, so reporting MaxRSS against ReqMem
    compares one rank against every rank. TRESUsageInTot carries the sum over
    ranks and is what the request should be read against; on a single-task job
    the two agree.

    Either figure is None when Slurm never sampled the step, as for a job still
    running, which keeps that apart from a job that used no measurable memory.
    Raises if accounting could not be read.
    """
    code, out, err = process.probe(
        ["sacct", "-j", jobid, "-n", "-P", "-o", "MaxRSS,TRESUsageInTot,NTasks"]
    )
    if code != 0:
        raise CommandError(f"could not read job {jobid}'s memory use: {err.strip() or code}")
    peaks, totals, tasks = [], [], 0
    for row in out.splitlines():
        parts = row.split("|")
        if len(parts) < 3:
            continue
        if parts[0].strip():
            peaks.append(_mem_to_mb(parts[0].strip()))
        used = _tres_mem_mb(parts[1])
        if used:
            totals.append(used)
        if parts[2].strip().isdigit():
            tasks = max(tasks, int(parts[2].strip()))
    return (
        max(peaks) if peaks else None,
        max(totals) if totals else None,
        tasks,
    )


_TOKEN = re.compile(r"\\(.)|%(\d*)(.?)")
_NUMERIC_TOKENS = "AabjJ"
_MAX_PAD = 10
_NO_ARRAY_TASK = "4294967294"


def _expand_log_pattern(path: str, fields: dict) -> str:
    """Expand the sbatch filename patterns sacct stores unexpanded.

    Follows man sbatch's FILENAME PATTERN section: a backslash suppresses the
    next symbol, a zero-pad width is capped at 10 and applies only to a numeric
    symbol, a trailing lone percent is dropped, and a symbol sbatch does not
    define is left in the name literally, which is what Slurm itself writes.
    %a on a job that is not an array becomes Slurm's own no-task value, and %b
    that value modulo 10, which is how the 4 in a non-array name arises.

    Returns an empty string only when a symbol is genuinely unresolvable from
    accounting, since a half-expanded path names a file that cannot exist, which
    is worse than admitting the log cannot be located.
    """
    raw = fields.get("raw_id", "")
    master, sep, task = fields.get("job_id", "").partition("_")
    array_task = task if sep else _NO_ARRAY_TASK
    values = {
        "%": "%",
        "A": master,
        "a": array_task,
        "b": str(int(array_task) % 10) if array_task.isdigit() else "",
        "J": raw,
        "j": raw,
        "N": fields.get("node", ""),
        "n": "0",
        "s": "batch",
        "t": "0",
        "r": "0",
        "u": fields.get("user", ""),
        "x": fields.get("name", ""),
    }
    failed = False

    def expand(match: re.Match) -> str:
        nonlocal failed
        escaped, width, symbol = match.groups()
        if escaped is not None:
            return escaped
        if not symbol:
            return ""
        if symbol not in values:
            return match.group(0)
        value = values[symbol]
        if not value:
            failed = True
            return ""
        if width and symbol in _NUMERIC_TOKENS:
            return value.zfill(min(int(width), _MAX_PAD))
        return value

    expanded = _TOKEN.sub(expand, path)
    return "" if failed else expanded


def expand_hostlist(nodelist: str) -> list[str]:
    """Return the individual node names in a Slurm hostlist.

    sacct and squeue write a multi-node allocation as a range such as
    node[1-4,7], so counting the field verbatim books one incident against a
    string rather than against each node, and splits one bad node's incidents
    across every allocation shape it appeared in.
    """
    compact = nodelist.strip()
    if not compact or compact.lower() in ("none assigned", "none"):
        return []
    if "[" not in compact:
        return [name for name in compact.split(",") if name]
    code, out, _ = process.probe(["scontrol", "show", "hostnames", compact])
    if code != 0:
        return [compact]
    return [name for name in out.split() if name]


def _first_node(nodelist: str) -> str:
    """Return the first node of a NodeList, which is what %N expands to for a batch step.

    Accounting records the list, so a name using %N is resolvable after the fact
    rather than only while the job runs.
    """
    if not nodelist or nodelist == "None assigned":
        return ""
    head = nodelist.split(",")[0]
    if "[" not in head:
        return head
    prefix, _, rest = head.partition("[")
    return prefix + rest.split("-")[0].split(",")[0].rstrip("]")


def job_output_paths(jobid: str) -> tuple[str, str]:
    """Return a job's (stdout, stderr) paths, each empty when it cannot be determined.

    Asks the controller first, which holds the expanded paths while the job is
    recent, then accounting, which keeps the unexpanded pattern long after
    MinJobAge has purged the job from scontrol. A pattern sacct stores relative is
    relative to the job's WorkDir, not to the caller's directory. The symbols are
    expanded against the JobID accounting recorded rather than the string the
    caller typed, since an array element named by its raw id would otherwise
    expand %a to the no-task value and name a file that was never written.

    Accounting records no path for a job submitted without one, and only then is
    the default sbatch writes assumed, and only for a job that has a batch step:
    an interactive allocation writes to the terminal and has no file to name. A
    pattern that is recorded but cannot be expanded yields nothing rather than the
    default, which would name a file the job never wrote.
    """
    code, out, _ = process.probe(["scontrol", "show", "job", jobid])
    if code == 0:
        live = {}
        for key in ("StdOut", "StdErr"):
            match = re.search(rf"{key}=(\S+)", out)
            if match and match.group(1) not in ("", "(null)"):
                live[key] = match.group(1)
        if live.get("StdOut"):
            return live["StdOut"], live.get("StdErr", "")

    code, out, _ = process.probe(
        [
            "sacct",
            "-j",
            jobid,
            "-n",
            "-P",
            "-o",
            "JobID,JobIDRaw,StdOut,StdErr,WorkDir,JobName,User,NodeList",
        ]
    )
    if code != 0:
        return "", ""
    rows = [line.split("|") for line in out.splitlines() if line.strip()]
    rows = [row for row in rows if len(row) >= 8]
    row = next((row for row in rows if "." not in row[0]), [])
    if not row:
        return "", ""
    has_batch_step = any(other[0].strip().endswith(".batch") for other in rows)
    fields = {
        "raw_id": row[1].strip(),
        "job_id": row[0].strip() or jobid,
        "user": row[6].strip(),
        "name": row[5].strip(),
        "node": _first_node(row[7].strip()),
    }
    workdir = row[4].strip()

    def resolve(recorded: str, default: str) -> str:
        if recorded:
            path = _expand_log_pattern(recorded, fields)
        elif workdir and has_batch_step:
            path = default
        else:
            path = ""
        if not path:
            return ""
        if not path.startswith("/"):
            return f"{workdir.rstrip('/')}/{path}" if workdir else ""
        return path

    raw = fields["raw_id"] or jobid
    stdout_path = resolve(row[2].strip(), f"slurm-{raw}.out")
    stderr_path = resolve(row[3].strip(), stdout_path)
    return stdout_path, stderr_path


def job_output_path(jobid: str) -> str:
    """Return a job's stdout path, or empty when it cannot be determined."""
    return job_output_paths(jobid)[0]


def job_output_tail(jobid: str, lines: int = 200) -> str:
    """Return the tail of a job's logs, or empty if none can be read.

    Reads stderr as well as stdout when the job wrote them to different files: a
    traceback lands on stderr, so scanning stdout alone misses the very message
    that explains the failure.
    """
    seen: list[str] = []
    for path in job_output_paths(jobid):
        if path and path not in seen:
            seen.append(path)
    chunks = []
    for path in seen:
        code, out, _ = process.probe(["tail", "-n", str(lines), path])
        if code == 0 and out:
            chunks.append(out)
    return "\n".join(chunks)


_BAD_NODE_STATES = (
    "DOWN",
    "DRAIN",
    "MAINT",
    "NOT_RESPONDING",
    "RESERVED",
    "COMPLETING",
    "FAIL",
    "POWER",
    "INVAL",
    "BLOCKED",
    "FUTURE",
    "UNKNOWN",
    "PERFCTRS",
    "NPC",
    "REBOOT",
)
"""Substrings of a scontrol State= field naming a node that cannot take new work.

Per man sinfo: PERFCTRS/NPC renders a node "not usable for any other jobs",
FUTURE is "not fully configured", and UNKNOWN means the state "has not yet been
determined", which every node reports briefly after a slurmctld restart. POWER
covers the POWER_DOWN, POWERED_DOWN, POWERING_DOWN and POWERING_UP spellings,
and REBOOT the REBOOT_REQUESTED and REBOOT_ISSUED ones.
"""


_UNSCHEDULABLE_CODES = (
    "down",
    "drain",
    "drng",
    "fail",
    "failg",
    "futr",
    "maint",
    "resv",
    "unk",
    "inval",
    "npc",
    "pow_dn",
    "pow_up",
)
"""sinfo short state codes for a node that will not take a new job."""


def is_schedulable_state(state: str) -> bool:
    """Return True if a sinfo %t code names a node that can still take work.

    A trailing * is a node that is not responding, which man sinfo says will not
    be allocated any new work whatever its base state, so it counts as not
    schedulable. The other suffixes, such as - for backfill-planned, do not.
    """
    code = state.strip().lower()
    if code.endswith("*"):
        return False
    code = code.rstrip("*-~#%$@")
    return not code.startswith(_UNSCHEDULABLE_CODES)


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
                "cpu_free": (_int_field(kv.get("CPUEfctv")) or _int_field(kv.get("CPUTot")))
                - _int_field(kv.get("CPUAlloc")),
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

    -D is passed because man sacct otherwise shows only the most recent record
    for a job id, and a requeued job has one record per incarnation. Without it
    a job preempted nine times and then cancelled reports as one cancellation,
    and the preemptions and node failures that caused the requeues are invisible.

    Raises if sacct fails, so a bad time string, an unknown user, or an
    unreachable slurmdbd is not reported as a window in which nothing ran.
    """
    cmd = ["sacct", "-X", "-D", "-n", "-P", "-o", fields, "-S", start, "-E", end]
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
    to ask for it separately or every ratio comes out zero. Raises when that query
    fails, since returning zero would report every account as unused rather than
    admitting the denominator is unknown.
    """
    code, out, err = process.probe(
        ["sshare", "-a", "-P", "-o", "Account,User,RawUsage", "-A", "root"]
    )
    if code != 0:
        raise CommandError(
            "could not read the root account's usage, which every ratio is measured "
            f"against: {err.strip() or code}"
        )
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
        parsed.append((name, _float_field(parts[2]), _float_field(parts[3]), raw_usage))
    if not root_usage:
        root_usage = _root_raw_usage()

    rows: list[dict] = []
    for name, raw_shares, norm_shares, raw_usage in parsed:
        rows.append(
            {
                "account": name,
                "raw_shares": raw_shares,
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
