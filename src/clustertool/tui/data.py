"""Panel data, gathered without any reference to the widgets that show it.

Each function returns a plain dataclass so it can be tested without starting an
app, which is where the parsing and failure handling are covered.
"""

import concurrent.futures
import dataclasses
import os
import pwd
import socket

from clustertool import site
from clustertool.process import CommandError


@dataclasses.dataclass(frozen=True)
class Identity:
    """Who is running the app, and where."""

    user: str
    full_name: str
    host: str
    site_name: str


def identity() -> Identity:
    """Return the caller's identity from the uid, never from the environment.

    The site name rather than the QoS cluster, which the site config documents as
    the cluster the admin qos commands write to and which would label every
    deployment with the packaged default.
    """
    from clustertool import slurm

    user = pwd.getpwuid(os.getuid()).pw_name
    try:
        full = slurm.user_fullnames([user]).get(user, "")
    except CommandError:
        full = ""
    return Identity(
        user=user,
        full_name=full,
        host=socket.gethostname().split(".")[0],
        site_name=site.site_name(),
    )


JOB_FIELD_NAMES = (
    "JobArrayID",
    "StateCompact",
    "State",
    "Partition",
    "TimeUsed",
    "Reason",
    "tres-alloc",
    "NodeList",
    "NumNodes",
)
"""The squeue fields the panel reads, in the order it asks for them.

JobArrayID rather than JobID: JobID prints the internal numeric id, which for an
array element is neither what the user submitted nor what scancel and the rest of
the CLI print. JobArrayID matched %i on every one of the 16,759 jobs queued when
this was checked. StateCompact rather than deriving the two-letter code here,
which is Slurm's table to own. NumNodes so the node column can name the head and
a count without expanding the hostlist, which costs a scontrol fork per job.

The reply is read back by name against this tuple rather than by position, so
reordering it, or asking for a different field, cannot silently put one column's
value in another column.
"""

JOB_FIELDS = ",".join(f"{name}:|" for name in JOB_FIELD_NAMES)

PENDING_CODES = ("PD", "CF")

EMPTY_NODELISTS = ("", "none assigned", "none", "(null)")


@dataclasses.dataclass(frozen=True)
class JobRow:
    """One of the caller's jobs, as the panel shows it."""

    jobid: str
    code: str
    state: str
    partition: str
    gpus: int
    elapsed: str
    reason: str
    nodelist: str
    nnodes: int
    tres: str

    @property
    def pending(self) -> bool:
        """True while the job is waiting rather than running."""
        return self.code in PENDING_CODES

    @property
    def assigned(self) -> bool:
        """True once Slurm has named nodes for the job."""
        return self.nodelist.strip().lower() not in EMPTY_NODELISTS

    @property
    def stated_reason(self) -> str:
        """The reason Slurm gives, when it gives one rather than the literal None.

        A job Slurm is setting up carries the string None, which reads in a panel
        as a wait with an unknown cause rather than as no wait at all.
        """
        return self.reason if self.reason and self.reason != "None" else ""

    @property
    def where(self) -> str:
        """The node column: where it runs, or why it is not running yet."""
        if self.assigned:
            from clustertool import slurm

            head = slurm.first_node(self.nodelist)
            return head if self.nnodes <= 1 else f"{head} +{self.nnodes - 1}"
        return f"({self.stated_reason})" if self.stated_reason else "-"


QUOTA_WORKERS = 6
"""How many quota lookups run at once.

Measured on a login node over 40 lab directories: one thread 6.9s, two 3.4s, four
1.7s, six 1.2s, eight 0.90s, sixteen 0.59s. Near-linear to eight and flat after,
so six buys almost all of it. This is a shared login node and every viewer pays
the concurrency, so the number stays modest rather than maximal.
"""

QUOTA_TIMEOUT_S = 45

LUSTRE = "lustre"
"""The only filesystem type with a per-user query worth making.

lfs quota -u answers in under a second. The site's other roots are NFS-fronted
and report per-user figures either slowly or not at all, so they are shown at lab
level only.
"""


@dataclasses.dataclass(frozen=True)
class QuotaRow:
    """One filesystem's usage, as the panel shows it."""

    label: str
    used: str
    quota: str
    percent: str
    error: str = ""

    @property
    def fraction(self) -> float | None:
        """Usage as a fraction of the quota, or None when no quota is set."""
        from clustertool import storage

        value = storage.percent_value(self.percent)
        return None if value < 0 else value / 100.0


@dataclasses.dataclass(frozen=True)
class StorageInfo:
    """Everything the storage panel shows, in the order it shows it."""

    home: QuotaRow | None
    labs: list[QuotaRow]
    mine: list[QuotaRow]


def home_quota() -> QuotaRow:
    """Return home usage from df, which is what the storage home command reads."""
    from clustertool import process

    home = os.path.expanduser("~")
    code, out, err = process.probe(["df", "-h", home], timeout=QUOTA_TIMEOUT_S)
    if code != 0:
        return QuotaRow("home", "-", "-", "-", error=_probe_error(code, err, "df"))
    lines = out.splitlines()
    if len(lines) < 2:
        return QuotaRow("home", "-", "-", "-", error="df printed no rows")
    fields = lines[-1].split()
    if len(fields) < 5:
        return QuotaRow("home", "-", "-", "-", error="df row was short")
    return QuotaRow("home", fields[2], fields[1], fields[4].rstrip("%") + "%")


def lab_quotas(user: str) -> list[QuotaRow]:
    """Return every lab directory's quota, worst first, querying them in parallel.

    Worst first because the panel is a side column: whichever directory is closest
    to its quota is the one worth seeing without scrolling. A directory with no
    quota set sorts last, since it cannot be close to one.
    """
    from clustertool import site, storage

    targets = storage.lab_targets(storage.user_groups(user), site.storage_lab_roots())
    with concurrent.futures.ThreadPoolExecutor(max_workers=QUOTA_WORKERS) as pool:
        rows = list(pool.map(_lab_quota, targets))
    rows.sort(key=lambda row: (-(row.fraction or -1), row.label))
    return rows


def _lab_quota(target: tuple[str, str]) -> QuotaRow:
    """Return one lab directory's quota row."""
    from clustertool import process, storage

    path, group = target
    label = _label(path, group)
    code, out, err = process.probe(
        storage.quota_cmd(path, group=group or None), timeout=QUOTA_TIMEOUT_S
    )
    parsed = storage.parse_quota_row(out) if code == 0 else None
    if not parsed:
        return QuotaRow(label, "-", "-", "-", error=_probe_error(code, err or out, "quota"))
    used, quota, disk, _files = parsed
    return QuotaRow(label, used, quota, disk)


def my_lustre_quotas(user: str) -> list[QuotaRow]:
    """Return the caller's own usage on each Lustre root, by mount point.

    Asked per mount rather than per lab directory, because a per-user quota is a
    property of the filesystem and one query covers every lab on it.
    """
    from clustertool import process, site, storage

    seen, rows = set(), []
    for root in site.storage_lab_roots():
        mount, kind = storage.mount_point(root)
        if kind != LUSTRE or mount in seen:
            continue
        seen.add(mount)
        code, out, err = process.probe(
            [site.tool("lfs"), "quota", "-u", user, "-h", mount], timeout=QUOTA_TIMEOUT_S
        )
        label = os.path.basename(mount.rstrip("/")) or mount
        parsed = storage.parse_quota_row(out) if code == 0 else None
        if not parsed:
            rows.append(QuotaRow(label, "-", "-", "-", error=_probe_error(code, err or out, "lfs")))
            continue
        used, quota, disk, _files = parsed
        rows.append(QuotaRow(label, used, quota, disk))
    return rows


def storage_info(user: str) -> StorageInfo:
    """Gather every storage figure the panel shows."""
    return StorageInfo(home=home_quota(), labs=lab_quotas(user), mine=my_lustre_quotas(user))


def _label(path: str, group: str) -> str:
    """Name a lab directory by its filesystem and its group.

    Both are needed: a user can belong to twenty labs across four filesystems, so
    either half alone names several rows.
    """
    from clustertool import storage

    mount, _ = storage.mount_point(path)
    filesystem = os.path.basename(mount.rstrip("/")) if mount else ""
    return f"{filesystem}/{group}" if filesystem and group else group or path


def _probe_error(code: int, err: str, tool: str) -> str:
    """Describe a failed lookup, naming the cause rather than the exit code."""
    if code == 127:
        return f"'{tool}' not found on this host"
    if code == 124:
        return f"{tool} timed out"
    return err.strip().splitlines()[0] if err.strip() else f"{tool} exited {code}"


def _count(text: str) -> int:
    """Return a squeue count field as an int, tolerating the range a pending job shows."""
    head = text.split("-")[0].strip()
    return int(head) if head.isdigit() else 0


def jobs(user: str) -> list[JobRow]:
    """Return the caller's jobs in one squeue call.

    The allocated TRES rather than the requested, since Slurm rounds a request up
    to a whole node or socket and the panel should show what the job holds. The
    field separator is asked for explicitly, because the default format pads to
    fixed widths and truncates a long TRES string.
    """
    from clustertool import process, slurm

    code, out, err = process.probe(
        ["squeue", "-h", "-u", user, "--Format=" + JOB_FIELDS], timeout=30
    )
    if code == 127:
        raise CommandError("'squeue' not found on this host")
    if code == 124:
        raise CommandError("squeue timed out; the controller is not answering")
    if code != 0:
        raise CommandError(f"could not read your jobs: {err.strip() or code}")
    rows = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) < len(JOB_FIELD_NAMES):
            continue
        field = dict(zip(JOB_FIELD_NAMES, (p.strip() for p in parts), strict=False))
        if not field["JobArrayID"]:
            continue
        tres = field["tres-alloc"]
        rows.append(
            JobRow(
                jobid=field["JobArrayID"],
                code=field["StateCompact"],
                state=field["State"],
                partition=field["Partition"],
                gpus=slurm.parse_gpu_count(tres),
                elapsed=field["TimeUsed"],
                reason=field["Reason"],
                nodelist=field["NodeList"],
                nnodes=_count(field["NumNodes"]),
                tres=tres,
            )
        )
    return rows
