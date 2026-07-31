"""Read-only Slurm QoS queries via sacctmgr, for the qos command group.

Each helper returns parsed data; the commands format it. Queries are scoped to
the site's Slurm cluster ([qos].cluster) unless a cluster is passed. The limit
builder maps the tool's flags to sacctmgr TRES specs.
"""

import re

from cluster_tools import process, site

_run = process.run

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def valid_name(name: str) -> bool:
    """Return True if a QoS name is safe to pass to sacctmgr.

    Rejects commas and whitespace so a stray name cannot be read as a list and
    create more than one QoS.
    """
    return bool(_NAME_RE.match(name))


def _cluster(cluster: str | None) -> str:
    return cluster or site.qos_cluster()


def _show(*args: str) -> list[str]:
    """Run a read-only `sacctmgr -n -P show ...` and return non-empty lines."""
    return [line for line in _run(["sacctmgr", "-n", "-P", "show", *args]).splitlines() if line]


def qos_exists(name: str) -> bool:
    """Return True if a QoS with exactly this name is defined."""
    return name in _show("qos", name, "format=Name")


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

    A non-empty result means the QoS is still referenced and must not be
    deleted. Rows are the raw Cluster|Account|User|Partition lines.
    """
    return _show("assoc", "where", f"qos={qos_name}", "format=Cluster,Account,User,Partition")


def build_limit_specs(
    gpu_per_user: int | None = None,
    node_per_user: int | None = None,
    group_gpu: int | None = None,
    job_gpu: int | None = None,
    jobs_per_user: int | None = None,
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
    if group_gpu is not None:
        specs.append(f"GrpTRES=gres/gpu={group_gpu}")
    if job_gpu is not None:
        specs.append(f"MaxTRES=gres/gpu={job_gpu}")
    if jobs_per_user is not None:
        specs.append(f"MaxJobsPU={jobs_per_user}")
    return specs
