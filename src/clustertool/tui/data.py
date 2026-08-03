"""Panel data, gathered without any reference to the widgets that show it.

Each function returns a plain dataclass so it can be tested without starting an
app, which is where the parsing and failure handling are covered.
"""

import collections
import dataclasses
import os
import pwd
import socket
import threading
import time

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

QUOTA_TIMEOUT_S = 15
"""How long one lookup may take.

A lab directory answers in 0.01 to 0.19s, so this is ample. It used to be 45,
which is what the CLI allows for a single lookup, but here it also bounds how
long quitting can block: nothing cancels a lookup in flight, and the interpreter
joins the thread running it before it exits.
"""

GATHER_DEADLINE_S = 12.0
"""How long the whole fan-out waits before giving up on whatever is left.

One unresponsive target held the panel for the full timeout while the other 39
had answered in 1.3s. A straggler is reported as still reading rather than
allowed to hold every other figure hostage.
"""

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
    files: str = "-"
    error: str = ""

    @property
    def disk_fraction(self) -> float | None:
        """Block usage as a fraction of the block quota, None when none is set."""
        return _fraction(self.percent)

    @property
    def files_fraction(self) -> float | None:
        """Inode usage as a fraction of the inode quota, None when none is set."""
        return _fraction(self.files)

    @property
    def fraction(self) -> float | None:
        """Whichever of the two quotas is closer to being reached.

        A directory stops being writable when it runs out of either blocks or
        inodes, so the binding one is the one worth a bar and a sort position. One
        real lab sat at 99% of its inode quota and 79% of its block quota.
        """
        both = [value for value in (self.disk_fraction, self.files_fraction) if value is not None]
        return max(both) if both else None

    @property
    def files_bound(self) -> bool:
        """True when inodes, not blocks, are what this directory will run out of."""
        disk, files = self.disk_fraction, self.files_fraction
        return files is not None and (disk is None or files > disk)

    @property
    def used_bytes(self) -> float:
        """The rendered usage as bytes, for ordering rows whose percentages tie."""
        from clustertool import storage

        return storage.used_bytes(self.used)


def _fraction(percent: str) -> float | None:
    """Return a percentage string as a fraction, or None when it says nothing."""
    from clustertool import storage

    value = storage.percent_value(percent)
    return None if value < 0 else value / 100.0


@dataclasses.dataclass(frozen=True)
class StorageInfo:
    """Everything the storage panel shows, in the order it shows it."""

    home: QuotaRow | None
    labs: list[QuotaRow]
    mine: list[QuotaRow]


def home_quota() -> QuotaRow:
    """Return home usage from df, which is what the storage home command reads.

    The home directory comes from the passwd entry rather than from HOME, which
    the caller can point anywhere, exactly as identity() reads the user from the
    uid rather than from the environment.
    """
    from clustertool import process

    home = pwd.getpwuid(os.getuid()).pw_dir
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
    rows = _fan_out(targets)
    rows.sort(key=_worst_first)
    return rows


def _fan_out(targets: list[tuple[str, str]]) -> list[QuotaRow]:
    """Look up every target on at most QUOTA_WORKERS threads, and stop waiting.

    Daemon threads rather than a thread pool: a pool joins its workers before the
    interpreter exits, so one unresponsive target made quitting the dashboard wait
    the lookup out. A target that has not answered by the deadline is reported as
    still reading rather than holding the other thirty-nine figures back.
    """
    queue = collections.deque(targets)
    done: dict[tuple[str, str], QuotaRow] = {}
    lock = threading.Lock()

    def worker() -> None:
        while True:
            with lock:
                if not queue:
                    return
                target = queue.popleft()
            try:
                row = _lab_quota(target)
            except Exception as exc:
                row = QuotaRow(_label(*target), "-", "-", "-", error=f"{type(exc).__name__}")
            with lock:
                done[target] = row

    threads = [
        threading.Thread(target=worker, daemon=True, name="clustertool-quota")
        for _ in range(min(QUOTA_WORKERS, len(targets)))
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + GATHER_DEADLINE_S
    for thread in threads:
        thread.join(max(deadline - time.monotonic(), 0.0))
    with lock:
        gathered = dict(done)
    return [
        gathered.get(target) or QuotaRow(_label(*target), "-", "-", "-", error="still reading")
        for target in targets
    ]


def _worst_first(row: QuotaRow) -> tuple:
    """Order rows by how much they need looking at.

    A row that could not be read comes first: it is the one fact the panel cannot
    show any other way, and a side column shows only its first dozen rows. Then
    the fullest, then those with no quota to be full of. Ties on percentage break
    on bytes held, since a directory holding data ranks above an empty one at the
    same nought percent.
    """
    fraction = row.fraction
    if row.error:
        return (0, 0.0, 0.0, row.label)
    if fraction is None:
        return (2, 0.0, -row.used_bytes, row.label)
    return (1, -fraction, -row.used_bytes, row.label)


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
    used, quota, disk, files = parsed
    return QuotaRow(label, used, quota, disk, files)


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
        used, quota, disk, files = parsed
        rows.append(QuotaRow(label, used, quota, disk, files))
    return rows


def storage_info(user: str) -> StorageInfo:
    """Gather every storage figure the panel shows."""
    return StorageInfo(home=home_quota(), labs=lab_quotas(user), mine=my_lustre_quotas(user))


def _label(path: str, group: str) -> str:
    """Name a lab directory by its group and then its filesystem.

    Both are needed: a user can belong to twenty labs across four filesystems, so
    either half alone names several rows. The group comes first because the label
    is cut from the tail in a side column, and with the filesystem first forty
    directories rendered as three distinct labels at eighty columns. Which lab is
    full is the actionable half.
    """
    from clustertool import storage

    mount, _ = storage.mount_point(path)
    filesystem = os.path.basename(mount.rstrip("/")) if mount else _filesystem_of(path)
    return f"{group}@{filesystem}" if filesystem and group else group or path


def _filesystem_of(path: str) -> str:
    """Name the filesystem from the path when the mount table cannot be read.

    Without this the label falls back to the group alone, and every one of a lab's
    directories then carries the same name with a different percentage. The site
    path prefix is dropped first, since every root here begins with it and the
    component after it is the one that names the filesystem.
    """
    prefix = site.path_prefix().strip("/")
    parts = [part for part in path.strip("/").split("/") if part]
    if prefix and parts and parts[0] == prefix:
        parts = parts[1:]
    return parts[0] if parts else ""


ERROR_WORDS = 6
"""How much of a tool's complaint is kept.

The site wrapper answers an unquotaed path with a hundred-character message and a
df table, and a row has room for neither.
"""


def _probe_error(code: int, err: str, tool: str) -> str:
    """Describe a failed lookup, naming the cause rather than the exit code."""
    if code == 127:
        return f"'{tool}' not found on this host"
    if code == 124:
        return f"{tool} timed out"
    first = err.strip().splitlines()[0].strip() if err.strip() else ""
    if not first:
        return "no quota reported" if code == 0 else f"{tool} exited {code}"
    return " ".join(first.split()[:ERROR_WORDS])


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
