"""Read-only Slurm QoS queries via sacctmgr, for the qos command group.

Each helper returns parsed data; the commands format it. Queries are scoped to
the site's Slurm cluster ([qos].cluster) unless a cluster is passed. The limit
builder maps the tool's flags to sacctmgr TRES specs.
"""

import re

from clustertool import process, site
from clustertool.process import CommandError

_run = process.run

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def valid_name(name: str) -> bool:
    """Return True if a QoS name is safe to pass to sacctmgr.

    Rejects commas and whitespace so a stray name cannot be read as a list and
    create more than one QoS, and a leading dash so sacctmgr cannot read the name
    as one of its own options.
    """
    return bool(_NAME_RE.match(name))


def _cluster(cluster: str | None) -> str:
    return cluster or site.qos_cluster()


def _show(*args: str) -> list[str]:
    """Run a read-only `sacctmgr -n -P show ...` and return non-empty lines.

    Raises on a failed query rather than returning nothing. sacctmgr answers a
    database it cannot reach with an error and no rows, which would otherwise
    read as "this user holds nothing" and let a write be planned against a read
    that never happened.
    """
    cmd = ["sacctmgr", "-n", "-P", "show", *args]
    code, out, err = process.probe(cmd)
    if code != 0:
        raise CommandError(f"could not read {args[0]} from sacctmgr: {err.strip() or code}")
    return [line for line in out.splitlines() if line]


def qos_exists(name: str) -> bool:
    """Return True if a QoS with this name is defined.

    sacctmgr treats QoS names case-insensitively, so a name differing only in case
    is the same QoS. Raises if the query fails, so an unreachable accounting
    database is never read as 'not defined'.
    """
    code, out, err = process.probe(["sacctmgr", "-n", "-P", "show", "qos", name, "format=Name"])
    if code != 0:
        raise CommandError(f"could not check whether QoS {name} exists: {err.strip() or code}")
    return any(line.strip().lower() == name.lower() for line in out.splitlines())


def account_exists(name: str, cluster: str | None = None) -> bool:
    """Return True if the account has any association on the cluster."""
    rows = _show(
        "assoc", "where", f"account={name}", f"cluster={_cluster(cluster)}", "format=Account"
    )
    return bool(rows)


def holder_rows(
    qos_name: str,
    cluster: str | None = None,
    partition: str | None = None,
    account_regex: str = "^",
) -> list[tuple[str, str, str]]:
    """Return (user, account, partition) rows for the user-level holders of a QoS.

    Keeps only rows with a non-empty user and partition whose account matches
    account_regex (an extended regex), mirroring the shell tool's holder query.
    """
    where = [f"cluster={_cluster(cluster)}", f"qos={qos_name}"]
    if partition:
        where.append(f"partition={partition}")
    pattern = re.compile(account_regex)
    rows = []
    for line in _show("assoc", "where", *where, "format=User,Account,Partition"):
        parts = line.split("|")
        if len(parts) != 3:
            continue
        user, account, part = parts
        if user and part and pattern.search(account):
            rows.append((user, account, part))
    return rows


def any_holders(qos_name: str) -> list[str]:
    """Return every association (user- or account-level, any cluster) that lists the QoS.

    A non-empty result means the QoS is still referenced. Rows are the raw
    Cluster|Account|User|Partition lines. Raises if the query fails.
    """
    cmd = ["sacctmgr", "-n", "-P", "show", "assoc", "where", f"qos={qos_name}"]
    cmd.append("format=Cluster,Account,User,Partition")
    code, out, err = process.probe(cmd)
    if code != 0:
        raise CommandError(f"could not check who holds QoS {qos_name}: {err.strip() or code}")
    return [line for line in out.splitlines() if line]


def partition_references(qos_name: str, cluster: str | None = None) -> dict[str, list[str]]:
    """Return {partition: [setting]} for every partition setting naming the QoS.

    The setting matters: QoS and AllowQos let jobs use it, while DenyQos bars
    them, so deleting the QoS means opposite things for the two. Reads the site's
    Slurm cluster unless another is given, and includes hidden and
    group-restricted partitions, which a plain 'scontrol show partition' leaves
    out. Names are matched case-insensitively, as Slurm treats them.
    """
    cmd = ["scontrol", "-a", "-M", _cluster(cluster), "show", "partition"]
    code, out, err = process.probe(cmd)
    if code != 0:
        raise CommandError(f"could not read partitions: {err.strip() or code}")
    wanted = qos_name.lower()
    found: dict[str, list[str]] = {}
    name = None
    for token in out.split():
        key, _, value = token.partition("=")
        if key == "PartitionName":
            name = value
        elif key in ("QoS", "AllowQos", "DenyQos") and name:
            if wanted in [v.strip().lower() for v in value.split(",")]:
                found.setdefault(name, [])
                if key not in found[name]:
                    found[name].append(key)
    return dict(sorted(found.items()))


def partitions_referencing(qos_name: str, cluster: str | None = None) -> list[str]:
    """Return the names of the partitions whose configuration references the QoS."""
    return list(partition_references(qos_name, cluster=cluster))


_DEFINITION_FIELDS = (
    ("Priority", "Priority"),
    ("MaxTRESPU", "Per-user max"),
    ("MaxTRESPA", "Per-account max"),
    ("GrpTRES", "Group total"),
    ("MaxTRES", "Per-job max"),
    ("MaxTRESPerNode", "Per-node max"),
    ("MaxJobsPU", "Per-user jobs"),
)


def definition(name: str) -> list[tuple[str, str]]:
    """Return the [(label, value)] limits a QoS carries, skipping the unset ones.

    A limit that can be written has to be readable, and sacctmgr's own listing is
    too wide to read; an empty field means the limit is not set.
    """
    fields = ",".join(field for field, _ in _DEFINITION_FIELDS)
    code, out, err = process.probe(
        ["sacctmgr", "-n", "-P", "show", "qos", name, f"format={fields}"]
    )
    if code != 0:
        raise CommandError(f"could not read QoS {name}: {err.strip() or code}")
    row = next((line for line in out.splitlines() if line.strip()), "")
    values = row.split("|")
    return [
        (label, value.strip())
        for (_, label), value in zip(_DEFINITION_FIELDS, values, strict=False)
        if value.strip()
    ]


def show_assoc_rows(user: str, account: str, cluster: str | None = None) -> list[str]:
    """Return the Partition|QOS rows for a user's associations in an account.

    Raises if the query fails, so a write is never planned against a read that did
    not happen.
    """
    cmd = [
        "sacctmgr",
        "-n",
        "-P",
        "show",
        "assoc",
        "where",
        f"user={user}",
        f"account={account}",
        f"cluster={_cluster(cluster)}",
        "format=Partition,QOS",
    ]
    code, out, err = process.probe(cmd)
    if code != 0:
        raise CommandError(
            f"could not read {user}'s associations in {account}: {err.strip() or code}"
        )
    return [line for line in out.splitlines() if line.strip()]


def cluster_exists(name: str) -> bool:
    """Return True if slurmdbd knows the cluster.

    sacctmgr answers a query scoped to an unknown cluster with an empty result and
    exit 0, so without this a mistyped -c reads as 'nothing holds it'.
    """
    code, out, err = process.probe(
        ["sacctmgr", "-n", "-P", "show", "cluster", name, "format=Cluster"]
    )
    if code != 0:
        raise CommandError(f"could not check cluster {name}: {err.strip() or code}")
    return any(line.strip().lower() == name.lower() for line in out.splitlines())


def partition_exists(name: str, cluster: str | None = None) -> bool:
    """Return True if the partition is configured on the cluster.

    slurmdbd holds no record of a cluster's partitions, so it accepts any
    partition name in an association: a typo makes a grant create an association
    no job can use, and makes a revoke match nothing while reporting success.
    Raises if the partition cannot be looked up at all, so a controller that is
    unreachable is not reported as a partition that does not exist.
    """
    cmd = ["scontrol", "-a", "-M", _cluster(cluster), "show", "partition", name]
    code, out, err = process.probe(cmd)
    if code == 0:
        return True
    if "not found" in (out + err).lower():
        return False
    raise CommandError(f"could not look up partition {name}: {err.strip() or code}")


def partition_known(name: str, cluster: str | None = None) -> bool:
    """Return True if the partition is configured, or still carries associations.

    A partition removed from slurm.conf leaves its associations behind, and
    clearing those is exactly what revoke and retire are for. Creating an
    association on such a name is still a mistake, so grant and sync use the
    stricter partition_exists instead.
    """
    if partition_exists(name, cluster=cluster):
        return True
    cmd = [
        "sacctmgr",
        "-n",
        "-P",
        "show",
        "assoc",
        "where",
        f"partition={name}",
        f"cluster={_cluster(cluster)}",
        "format=Partition",
    ]
    code, out, _ = process.probe(cmd)
    return code == 0 and bool(out.strip())


def jobs_using(qos_name: str, cluster: str | None = None) -> int:
    """Return how many queued or running jobs carry the QoS.

    Deleting a QoS that live jobs still reference leaves them pointing at a
    definition that is gone. The states are named rather than left to squeue's
    default, which per man squeue covers only pending, running and completing and
    so would miss a suspended job that will resume still carrying the QoS. Raises
    if the query fails, so an unreachable controller is never read as 'no jobs'.
    """
    code, out, err = process.probe(
        [
            "squeue",
            "-h",
            "-M",
            _cluster(cluster),
            "-t",
            "pending,running,suspended,completing",
            "-o",
            "%q",
        ]
    )
    if code != 0:
        raise CommandError(f"could not check jobs using QoS {qos_name}: {err.strip() or code}")
    wanted = qos_name.lower()
    return sum(1 for field in out.split() if field.lower() == wanted)


def _plan_targets(plan: list[list[str]]) -> set[tuple[str, str, str, str]]:
    """Return the (cluster, account, user, partition) associations a revoke plan clears."""
    keys = {"cluster", "account", "partition", "user", "name"}
    targets = set()
    for cmd in plan:
        fields: dict[str, str] = {}
        for token in cmd:
            key, sep, value = token.partition("=")
            if sep and key in keys:
                fields["user" if key == "name" else key] = value
        if "user" in fields and "account" in fields:
            targets.add(
                (
                    fields.get("cluster", ""),
                    fields["account"],
                    fields["user"],
                    fields.get("partition", ""),
                )
            )
    return targets


def uncovered_holders(qos_name: str, plan: list[list[str]]) -> list[str]:
    """Return the associations holding a QoS that a revoke plan would not clear.

    Rows are the raw Cluster|Account|User|Partition lines from any_holders. An
    empty result means the plan covers every holder on every cluster, so deleting
    the QoS afterwards removes nothing still in force. Account-level holders
    (empty User) and holders with no partition are never covered by a
    partition-scoped sweep, so they always come back here.
    """
    covered = _plan_targets(plan)
    uncovered = []
    for line in any_holders(qos_name):
        parts = [field.strip() for field in line.split("|")]
        if len(parts) != 4 or tuple(parts) not in covered:
            uncovered.append(line)
    return uncovered


def flatten_users(values: tuple[str, ...]) -> list[str]:
    """Flatten repeated, comma-separated -u values into an ordered unique list."""
    users: list[str] = []
    for value in values:
        for name in value.split(","):
            name = name.strip()
            if name and name not in users:
                users.append(name)
    return users


def get_accounts(user: str, cluster: str | None = None, account_regex: str = "^") -> list[str]:
    """Return the sorted distinct accounts a user belongs to, filtered by regex."""
    pattern = re.compile(account_regex)
    accounts = {
        line
        for line in _show(
            "assoc", "where", f"user={user}", f"cluster={_cluster(cluster)}", "format=Account"
        )
        if pattern.search(line)
    }
    return sorted(accounts)


def account_base_members(account: str, cluster: str | None = None) -> list[str]:
    """Return the users holding the account's base association, sorted.

    The base association is the one with no partition. Raises if the query fails.
    """
    cmd = [
        "sacctmgr",
        "-n",
        "-P",
        "show",
        "assoc",
        "where",
        f"account={account}",
        f"cluster={_cluster(cluster)}",
        "format=User,Partition",
    ]
    code, out, err = process.probe(cmd)
    if code != 0:
        raise CommandError(f"could not read members of {account}: {err.strip() or code}")
    users = set()
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) == 2 and parts[0].strip() and not parts[1].strip():
            users.add(parts[0].strip())
    return sorted(users)


def read_assoc(
    user: str, account: str, partition: str, cluster: str | None = None
) -> tuple[str, str, list[str]] | None:
    """Return (qos_csv, default_qos, raw_entries) for a partition-scoped association.

    None means the association does not exist; the qos_csv may be empty when the
    association exists but carries no QoS of its own. raw_entries is the list
    sacctmgr returned with its signs intact, since a minus entry is a filter the
    association really carries and dropping one silently hands back the QoS it
    was filtering out.

    woplimits and withrawqos ask sacctmgr for what this association sets rather
    than what it inherits. Without them a QoS pushed down from the parent reads
    as the association's only entry, and a revoke would then delete the whole
    association, taking its fairshare, limits and recorded usage with it, to
    remove a QoS it never held.
    """
    lines = _show(
        "assoc",
        "woplimits",
        "withrawqos",
        "where",
        f"user={user}",
        f"account={account}",
        f"partition={partition}",
        f"cluster={_cluster(cluster)}",
        "format=User,QOS,DefaultQOS",
    )
    if not lines:
        return None
    parts = lines[0].split("|")
    if len(parts) != 3 or not parts[0]:
        return None
    raw = [entry.strip() for entry in parts[1].split(",") if entry.strip()]
    return ",".join(_held_qos(parts[1])), parts[2], raw


_CLEAR_DEFAULT = "-1"
"""What man sacctmgr gives for clearing DefaultQOS when nothing is left to inherit."""


def _held_qos(raw: str) -> list[str]:
    """Return the QoS names an association holds, from sacctmgr's raw list.

    withrawqos prefixes each name with nothing, + or -, per man sacctmgr, where
    a minus records a QoS filtered out rather than held. Callers compare plain
    names, so the sign is resolved here: without this an already-granted QoS
    reads as absent and the grant plans a change sacctmgr answers with "Nothing
    modified" and exit 1, which aborts the rest of the plan.
    """
    held = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or entry.startswith("-"):
            continue
        held.append(entry.removeprefix("+"))
    return held


def _strip_names(partition: str) -> list[str]:
    """Return the QoS names to strip on grant: the configured set plus the partition."""
    names = list(site.qos_grant_strip())
    if partition not in names:
        names.append(partition)
    return names


def grant_plan(
    user: str, account: str, partition: str, qos_name: str, default_qos: str, cluster: str | None
) -> list[list[str]]:
    """Build the sacctmgr commands to grant qos_name to (user, account) on a partition.

    Creates the association if absent (with the QoS list set exactly), otherwise
    adds the QoS, fixes the default, and strips the catch-all and partition-named
    QoS. A DefaultQOS has to be in the association's QoS list, so the default is
    added alongside when it is not there already. Returns an empty plan when
    nothing needs to change.
    """
    resolved = _cluster(cluster)
    where = [
        "where",
        f"user={user}",
        f"account={account}",
        f"partition={partition}",
        f"cluster={resolved}",
    ]
    assoc = read_assoc(user, account, partition, cluster=resolved)
    if assoc is None:
        qlist = qos_name if default_qos == qos_name else f"{qos_name},{default_qos}"
        return [
            [
                "sacctmgr",
                "-i",
                "add",
                "user",
                f"name={user}",
                f"account={account}",
                f"partition={partition}",
                f"cluster={resolved}",
                f"fairshare={site.qos_grant_fairshare()}",
                f"qos={qlist}",
                f"defaultqos={default_qos}",
            ]
        ]
    current, default, _raw = assoc
    current_list = [entry for entry in current.split(",") if entry]
    plan = []
    add = [name for name in dict.fromkeys((qos_name, default_qos)) if name not in current_list]
    if add:
        plan.append(["sacctmgr", "-i", "modify", "user", *where, "set", f"QOS+={','.join(add)}"])
    if default != default_qos:
        plan.append(
            ["sacctmgr", "-i", "modify", "user", *where, "set", f"DefaultQOS={default_qos}"]
        )
    keep = (qos_name, default_qos)
    strip = [name for name in _strip_names(partition) if name not in keep and name in current_list]
    if strip:
        plan.append(["sacctmgr", "-i", "modify", "user", *where, "set", f"QOS-={','.join(strip)}"])
    return plan


def revoke_plan(
    user: str, account: str, partition: str, qos_name: str, cluster: str | None
) -> list[list[str]]:
    """Build the sacctmgr commands to remove qos_name from (user, account) on a partition.

    Deletes the association when the QoS was its only entry; otherwise moves the
    default off the QoS first when needed, then removes it. Returns an empty plan
    when the association is absent or does not carry the QoS.
    """
    resolved = _cluster(cluster)
    assoc = read_assoc(user, account, partition, cluster=resolved)
    if assoc is None:
        return []
    current, default, raw = assoc
    current_list = [entry for entry in current.split(",") if entry]
    if qos_name not in current_list:
        return []
    if len(raw) == 1:
        return [
            [
                "sacctmgr",
                "-i",
                "delete",
                "user",
                "where",
                f"cluster={resolved}",
                f"name={user}",
                f"account={account}",
                f"partition={partition}",
            ]
        ]
    where = [
        "where",
        f"user={user}",
        f"account={account}",
        f"partition={partition}",
        f"cluster={resolved}",
    ]
    plan = []
    if default == qos_name:
        new_default = next((entry for entry in current_list if entry != qos_name), _CLEAR_DEFAULT)
        plan.append(
            ["sacctmgr", "-i", "modify", "user", *where, "set", f"DefaultQOS={new_default}"]
        )
    plan.append(["sacctmgr", "-i", "modify", "user", *where, "set", f"QOS-={qos_name}"])
    return plan


def revoke_targets_plan(
    qos_name: str,
    users: list[str],
    partition: str,
    cluster: str | None = None,
    account_regex: str = "^",
) -> list[list[str]]:
    """Build the combined revoke plan for the given users and partition.

    Expands the 'all' keyword: partition 'all' resolves to every partition that
    holds the QoS, and users ['all'] to every user holding it on those
    partitions (scoped by account_regex).
    """
    if partition == "all":
        partitions = sorted(
            {row[2] for row in holder_rows(qos_name, cluster=cluster, account_regex=account_regex)}
        )
    else:
        partitions = [partition]
    if users == ["all"]:
        rows = holder_rows(qos_name, cluster=cluster, account_regex=account_regex)
        user_list = sorted({row[0] for row in rows if row[2] in partitions})
    else:
        user_list = users
    plan = []
    for user in user_list:
        accounts = get_accounts(user, cluster=cluster, account_regex=account_regex)
        for part in partitions:
            for account in accounts:
                plan += revoke_plan(user, account, part, qos_name, cluster)
    return plan


def build_limit_specs(
    gpu_per_user: int | None = None,
    node_per_user: int | None = None,
    group_gpu: int | None = None,
    job_gpu: int | None = None,
    jobs_per_user: int | None = None,
    account_gpu: int | None = None,
) -> list[str]:
    """Build the sacctmgr `set` specs for QoS limits, in the tool's fixed order.

    Per-user node and GPU caps merge into one MaxTRESPU spec (passing MaxTRESPU
    twice is unreliable). A value of -1 clears that limit.
    """
    specs = []
    per_user = []
    if node_per_user is not None:
        per_user.append(f"node={node_per_user}")
    if gpu_per_user is not None:
        per_user.append(f"gres/gpu={gpu_per_user}")
    if per_user:
        specs.append("MaxTRESPU=" + ",".join(per_user))
    if account_gpu is not None:
        specs.append(f"MaxTRESPA=gres/gpu={account_gpu}")
    if group_gpu is not None:
        specs.append(f"GrpTRES=gres/gpu={group_gpu}")
    if job_gpu is not None:
        specs.append(f"MaxTRES=gres/gpu={job_gpu}")
    if jobs_per_user is not None:
        specs.append(f"MaxJobsPU={jobs_per_user}")
    return specs
