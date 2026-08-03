"""Panel data, gathered without any reference to the widgets that show it.

Each function returns a plain dataclass so it can be tested without starting an
app, which is where the parsing and failure handling are covered.
"""

import collections
import dataclasses
import os
import pwd
import socket
import statistics
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

_QUOTA_SLOTS = threading.Semaphore(QUOTA_WORKERS)
"""Concurrent lookups allowed across the whole process, not per fan-out.

A per-fan-out count is not a cap: the deadline releases the caller while the
abandoned workers are still in their lookups, so a second refresh reached twelve
against a documented six. Every lookup takes a slot, so overlapping batches share
the same six. An abandoned lookup gives its slot back when it times out, which is
why that timeout has to be shorter than the gather deadline.
"""

QUOTA_TIMEOUT_S = 8
"""How long one lookup may take.

A lab directory answers in 0.01 to 0.19s, so this is ample. It has to stay below
GATHER_DEADLINE_S, or a lookup can never reach its own timeout and every slow one
is reported as unfinished rather than as timed out.
"""

GATHER_DEADLINE_S = 10.0
"""How long the lab fan-out waits before giving up on whatever is left.

One unresponsive target held the panel for the full timeout while the other 39
had answered in 1.3s. A straggler is reported as unfinished rather than allowed
to hold every other figure hostage.
"""

STORAGE_DEADLINE_S = 14.0
"""How long the whole gather may take, across all three of its parts.

The parts run side by side under one deadline rather than one after another. In
series, and with only the lab fan-out bounded, a stale Lustre mount still held
quitting for the df timeout plus the fan-out deadline plus two lfs timeouts, which
came to longer than the unbounded version it replaced.
"""

STILL_READING = "unfinished"
"""What a lookup that has not answered by the deadline is marked with.

Distinct from a lookup that failed: a failure is a fact about the filesystem and
belongs at the top of the panel, whereas an unfinished one is a fact about this
refresh and belongs at the bottom. Sorting the two together let a slow filesystem
put forty unfinished rows above every real figure.
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
    def pending(self) -> bool:
        """True when this lookup simply did not finish in time."""
        return self.error == STILL_READING

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
    stop = threading.Event()

    def worker() -> None:
        while not stop.is_set():
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
    stop.set()
    with lock:
        gathered = dict(done)
    return [
        gathered.get(target) or QuotaRow(_label(*target), "-", "-", "-", error=STILL_READING)
        for target in targets
    ]


def _worst_first(row: QuotaRow) -> tuple:
    """Order rows by how much they need looking at.

    A row that could not be read comes first: it is the one fact the panel cannot
    show any other way, and a side column shows only its first dozen rows. Then
    the fullest, then those with no quota to be full of, and last the ones that
    simply did not finish, which say nothing about the filesystem and would
    otherwise bury every real figure when one mount is slow. Ties on percentage
    break on bytes held, since a directory holding data ranks above an empty one
    at the same nought percent.
    """
    fraction = row.fraction
    if row.pending:
        return (3, 0.0, 0.0, row.label)
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
    with _QUOTA_SLOTS:
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
    """Gather every storage figure the panel shows, under one deadline.

    The three parts run side by side on daemon threads. In series each carried its
    own timeout on a thread the interpreter joins at exit, so a stale mount held
    quitting for their sum. Whatever has not arrived by the deadline is reported as
    unfinished rather than waited for.
    """
    home: list = []
    labs: list = []
    mine: list = []
    work = (
        (home, home_quota),
        (labs, lambda: lab_quotas(user)),
        (mine, lambda: my_lustre_quotas(user)),
    )
    threads = [
        threading.Thread(target=_collect, args=(box, call), daemon=True, name="clustertool-storage")
        for box, call in work
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + STORAGE_DEADLINE_S
    for thread in threads:
        thread.join(max(deadline - time.monotonic(), 0.0))
    return StorageInfo(
        home=_taken(home, QuotaRow("home", "-", "-", "-", error=_why(home))),
        labs=_taken(labs, []),
        mine=_taken(mine, []),
    )


def _collect(box: list, call) -> None:
    """Run call and record (True, result), or (False, why) when it raises.

    The reason is kept rather than dropped: a panel that says only that something
    could not be read is far less use than one naming the tool that did not answer.
    """
    try:
        box.append((True, call()))
    except Exception as exc:
        box.append((False, _short_reason(exc)))


def _taken(box: list, fallback):
    """Return what a collected call produced, or the fallback when it has none."""
    return box[0][1] if box and box[0][0] else fallback


def _why(box: list) -> str:
    """Return why a collected call has no result: its reason, or that it is unfinished."""
    if not box:
        return STILL_READING
    return "" if box[0][0] else box[0][1]


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

NOT_TRACKED = "no quota on this filesystem"
"""What a df table in place of a quota reply means.

The site tool prints one, and exits zero, for a path whose filesystem it does not
track. Quoting its header back as the error read as a parse failure.
"""


def _probe_error(code: int, err: str, tool: str) -> str:
    """Describe a failed lookup, naming the cause rather than the exit code."""
    if code == 127:
        return f"'{tool}' not found on this host"
    if code == 124:
        return f"{tool} timed out"
    first = err.strip().splitlines()[0].strip() if err.strip() else ""
    if first.startswith("Filesystem") or first.startswith("command: df"):
        return NOT_TRACKED
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


STANDING_DAYS = 7
"""How far back the standing panel looks, in days."""

STANDING_TIMEOUT_S = 30

RECENT_FIELDS = ("JobID", "State", "Elapsed", "AllocTRES", "AdminComment")
"""The sacct fields the standing panel reads, in the order it asks for them."""

TERMINAL_STATES = ("COMPLETED", "CANCELLED", "FAILED", "TIMEOUT", "OUT_OF_MEMORY", "PREEMPTED")
"""Ended states worth counting separately; any other ended state groups as other."""

UNFINISHED_STATES = (
    "RUNNING",
    "PENDING",
    "SUSPENDED",
    "REQUEUED",
    "REQUEUE_HOLD",
    "RESIZING",
    "CONFIGURING",
    "COMPLETING",
)
"""States of a job that has not ended, and so does not belong in a window count.

The window says how recent work went. Counting a running job in it put a user
with eleven running jobs and nothing finished on "11 jobs: 11 other", and the
jobs panel already shows what is running.
"""

STANDING_DEADLINE_S = 12.0
"""How long the whole standing gather may take, across all of its parts.

Every query but the sacct one goes through a helper that passes no timeout, and
without a deadline one hung call left the panel saying it was reading for good,
with the in-flight guard set so no later refresh could recover it.
"""


@dataclasses.dataclass(frozen=True)
class Standing:
    """Where the caller stands: share, GPU cap, and how recent work went."""

    fairshare: list[tuple[str, str]]
    gpus_used: int
    gpu_cap: int | None
    account: str
    account_gpus: int
    account_cap: int | None
    caps_known: bool
    days: int
    states: dict[str, int]
    measured: int
    cpu: int | None
    mem: int | None
    gpu: int | None
    gpu_jobs: int
    note: str = ""
    """Why the efficiency half is missing, when it is."""

    @property
    def total(self) -> int:
        """How many jobs ended in the window, whether or not they carry metrics."""
        return sum(self.states.values())


def fairshare_rows(user: str) -> list[tuple[str, str]]:
    """Return the caller's fairshare per account, highest share first."""
    from clustertool import slurm

    rows = slurm.user_fairshare(user)
    return sorted(rows, key=lambda row: -_share(row[1]))


def _share(text: str) -> float:
    """Read a fairshare score, treating an unreadable one as the lowest."""
    try:
        return float(text)
    except ValueError:
        return -1.0


@dataclasses.dataclass(frozen=True)
class GpuStanding:
    """What the caller holds against their cap, and their account against its."""

    used: int
    cap: int | None
    account: str
    account_gpus: int
    account_cap: int | None
    caps_known: bool


def gpu_standing(user: str) -> GpuStanding:
    """Return the caller's GPUs and cap, and their account's GPUs and cap.

    Both levels, because either can be what stops a job starting and they are
    different numbers: this site allows a user 16 and their account 96.

    Both counts are restricted to the partitions the capped QoS is set on. Anywhere
    else does not count toward the cap, and counting it does not merely overstate:
    one user holding 239 GPUs on the requeue partition, and none on a base
    partition, was shown as 239 of 16 in the color that means no room left.

    The account is the one the caller's own jobs run under, not their default
    account. At this site every base-partition job runs under a prefixed account
    while the default is the unprefixed one, so the default named an account with
    no usage for all 43 users then running.
    """
    from clustertool import site, slurm

    used, mine = slurm.user_gpus_by_account(user, slurm.BASE_PARTITIONS)
    try:
        cap, account_cap = slurm.qos_gpu_caps()
        caps_known = True
    except CommandError:
        cap, account_cap, caps_known = None, None, False
    totals = slurm.gpu_by_account(slurm.BASE_PARTITIONS)
    account = _charged_account(user, mine, totals, site.lab_account_prefix())
    return GpuStanding(
        used=used,
        cap=cap,
        account=account,
        account_gpus=totals.get(account, 0),
        account_cap=account_cap,
        caps_known=caps_known,
    )


def _charged_account(user: str, mine: dict[str, int], totals: dict[str, int], prefix: str) -> str:
    """Name the account the caller's capped usage is charged to.

    Whichever of their own running jobs holds the most, since that is the account
    whose ceiling they are actually working against. With nothing running there is
    no such account, so their default is used, prefixed to match the accounts this
    QoS governs, and only when that names one Slurm reports.
    """
    from clustertool import slurm

    if mine:
        return max(mine.items(), key=lambda item: item[1])[0]
    try:
        default = slurm.default_account(user)
    except CommandError:
        return ""
    for candidate in (f"{prefix}{default}", default):
        if candidate in totals:
            return candidate
    return ""


def recent_work(user: str, days: int = STANDING_DAYS) -> tuple[dict[str, int], list[tuple]]:
    """Return (state counts, per-job metrics) for the caller's jobs in the window.

    One sacct call over a window rather than jobscope's select-then-fetch, which
    resolves a window to explicit job ids and asks sacct for them by id: that took
    over sixty seconds for this caller's 558 ids where the window query takes
    0.05s. The metric blobs are still decoded by jobscope, which owns that format.
    """
    from jobscope import blob

    from clustertool import process

    code, out, err = process.probe(
        [
            "sacct",
            "-u",
            user,
            "-S",
            f"now-{days}days",
            "-X",
            "-P",
            "-n",
            "--units=G",
            "-o",
            ",".join(RECENT_FIELDS),
        ],
        timeout=STANDING_TIMEOUT_S,
    )
    if code != 0:
        raise CommandError(_probe_error(code, err, "sacct"))
    states: dict[str, int] = {}
    metrics = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) < len(RECENT_FIELDS):
            continue
        field = dict(zip(RECENT_FIELDS, (p.strip() for p in parts), strict=False))
        head = field["State"].split()[0] if field["State"].split() else ""
        if not head or head in UNFINISHED_STATES:
            continue
        states[head if head in TERMINAL_STATES else "OTHER"] = (
            states.get(head if head in TERMINAL_STATES else "OTHER", 0) + 1
        )
        stats = blob.decode_admin_comment(field["AdminComment"]) if field["AdminComment"] else None
        measured = blob.blob_metrics(stats) if stats else None
        if measured is not None:
            metrics.append(measured)
    return states, metrics


def standing(user: str, days: int = STANDING_DAYS) -> Standing:
    """Gather everything the standing panel shows.

    The three parts run side by side under one deadline and fail independently.
    Sharing a failure was wrong twice over: an sshare or squeue error took the whole
    panel down where only the efficiency half was ever meant to degrade, and with no
    deadline a single hung call left the panel reading for good, its in-flight guard
    set so no later refresh could recover.
    """
    share: list = []
    gpus: list = []
    recent: list = []
    work = (
        (share, lambda: fairshare_rows(user)),
        (gpus, lambda: gpu_standing(user)),
        (recent, lambda: recent_work(user, days)),
    )
    threads = [
        threading.Thread(
            target=_collect, args=(box, call), daemon=True, name="clustertool-standing"
        )
        for box, call in work
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + STANDING_DEADLINE_S
    for thread in threads:
        thread.join(max(deadline - time.monotonic(), 0.0))
    rows = _taken(share, [])
    caps = _taken(gpus, GpuStanding(0, None, "", 0, None, False))
    states, metrics = _taken(recent, ({}, []))
    note = _why(recent)
    gpu_values = [entry[2] for entry in metrics if entry[2] is not None]
    return Standing(
        fairshare=rows,
        gpus_used=caps.used,
        gpu_cap=caps.cap,
        account=caps.account,
        account_gpus=caps.account_gpus,
        account_cap=caps.account_cap,
        caps_known=caps.caps_known,
        days=days,
        states=states,
        measured=len(metrics),
        cpu=_median([entry[0] for entry in metrics]),
        mem=_median([entry[1] for entry in metrics]),
        gpu=_median(gpu_values),
        gpu_jobs=len(gpu_values),
        note=note,
    )


def _median(values: list[int]) -> int | None:
    """Return the rounded median, or None when there is nothing to take one of.

    The median rather than the mean. These distributions are bimodal: of this
    caller's 72 measured jobs, 35 used no CPU at all while a handful of GPU jobs
    ran near 100%, which put the GPU mean at 28% against a median of 10%. The
    median describes the typical job, and the panel says which it is showing.
    """
    return round(statistics.median(values)) if values else None


def _short_reason(exc: BaseException) -> str:
    """Name a failure in a few words, for a panel with one line to spare."""
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return " ".join(text.split()[:ERROR_WORDS])
