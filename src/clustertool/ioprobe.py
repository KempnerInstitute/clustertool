"""Filesystem responsiveness probe used by diag io-probe.

Not a benchmark: a seconds-long probe against a target directory that measures
bounded sequential write (fsync included) and read (page cache dropped first,
and confirmed dropped) throughput plus small-file create/stat/delete latency.

All sizes and rates are MiB and MiB/s. The write buffer is filled with fresh
random bytes per chunk, since a compressing or deduplicating backend does not
store a repeated or zero-filled one, and the figure would then be fiction.
"""

import json
import os
import shutil
import socket
import time

CHUNK = 4 * 1024 * 1024
_MIB = 1024.0 * 1024.0

_MEMORY_FS_MAGIC = frozenset({0x01021994, 0x858458F6})
"""statfs f_type for tmpfs and ramfs, from the kernel's magic.h.

Neither is storage, so a probe of one measures memory. posix_fadvise reports
success there while evicting nothing, so the cache-dropped check cannot catch
it on its own.
"""


class ProbeError(RuntimeError):
    """Raised when the probe cannot set up or complete its IO."""


def measure_write(path, size_mb):
    """Write about size_mb in whole CHUNK pieces with fsync; return (mib_per_s, mib_written).

    Each chunk is fresh random data. A repeated buffer is deduplicated and a
    zero-filled one is compressed away by the reduction every VAST and many
    Lustre backends run, so either would measure the backend's ability to
    recognize the data rather than to store it.
    """
    chunks = max(1, int(size_mb * _MIB) // CHUNK)
    buffers = [os.urandom(CHUNK) for _ in range(chunks)]
    start = time.monotonic()
    with open(path, "wb") as handle:
        for chunk in buffers:
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    elapsed = time.monotonic() - start
    total_mb = chunks * CHUNK / _MIB
    return (total_mb / elapsed if elapsed > 0 else 0.0), total_mb


def is_memory_filesystem(path) -> bool:
    """Return True if path sits on tmpfs or ramfs, which are memory, not storage."""
    try:
        return os.statvfs(path).f_fsid is not None and _fs_magic(path) in _MEMORY_FS_MAGIC
    except OSError:
        return False


def _fs_magic(path) -> int:
    """Return the statfs f_type for a path, or 0 when it cannot be read."""
    try:
        with open("/proc/self/mountinfo", encoding="utf-8", errors="replace") as handle:
            mounts = handle.read()
    except OSError:
        return 0
    target = os.path.realpath(path)
    best, fstype = "", ""
    for line in mounts.splitlines():
        head, _, tail = line.partition(" - ")
        fields = head.split()
        if len(fields) < 5:
            continue
        point = fields[4]
        if (target == point or target.startswith(point.rstrip("/") + "/")) and len(point) > len(
            best
        ):
            best, fstype = point, tail.split()[0] if tail.split() else ""
    return {"tmpfs": 0x01021994, "ramfs": 0x858458F6}.get(fstype, 0)


def _drop_cache(path) -> bool:
    """Ask the kernel to forget a file's pages; return True when they went.

    posix_fadvise is advisory: POSIX_FADV_DONTNEED returns success on tmpfs
    while evicting nothing, so the return value alone cannot be trusted. The
    pages are checked afterwards with mmap plus mincore, which reports which of
    them are still resident.
    """
    advise = getattr(os, "posix_fadvise", None)
    if advise is None:
        return False
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return False
    try:
        advise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    except OSError:
        return False
    finally:
        os.close(fd)
    return not is_memory_filesystem(path)


def measure_read(path):
    """Re-read the file in CHUNK pieces; return (mib_per_s, from_cache).

    The page cache is dropped first, so the figure measures the filesystem rather
    than memory. from_cache is True when the pages did not actually go, and the
    number is therefore cache-assisted. On a network filesystem the data was
    written seconds earlier, so a dropped client cache still leaves the server's
    own cache in play.
    """
    size_mb = os.path.getsize(path) / _MIB
    dropped = _drop_cache(path)
    start = time.monotonic()
    with open(path, "rb") as handle:
        while handle.read(CHUNK):
            pass
    elapsed = time.monotonic() - start
    rate = size_mb / elapsed if elapsed > 0 else 0.0
    return rate, not dropped


def measure_meta(dirpath, count):
    """Create, stat, then delete count empty files; return mean ms per op by phase."""
    names = [os.path.join(dirpath, f"meta{i:05d}") for i in range(count)]
    t0 = time.monotonic()
    for name in names:
        open(name, "w").close()
    t1 = time.monotonic()
    for name in names:
        os.stat(name)
    t2 = time.monotonic()
    for name in names:
        os.unlink(name)
    t3 = time.monotonic()

    def per(start, end):
        return (end - start) * 1000.0 / count

    return {"create": per(t0, t1), "stat": per(t1, t2), "delete": per(t2, t3)}


def verdict(metrics, gates):
    """Return (status, reasons). REPORT when no gate is set; else PASS or FAIL."""
    reasons = []
    gated = False
    if gates.get("min_write") is not None:
        gated = True
        if metrics["write_mbs"] < gates["min_write"]:
            reasons.append(
                f"write {metrics['write_mbs']:.1f} MiB/s below --min-write {gates['min_write']:.1f}"
            )
    if gates.get("min_read") is not None:
        gated = True
        if metrics["read_mbs"] < gates["min_read"]:
            reasons.append(
                f"read {metrics['read_mbs']:.1f} MiB/s below --min-read {gates['min_read']:.1f}"
            )
    if gates.get("max_meta_ms") is not None:
        gated = True
        phase, worst = max(metrics["meta_ms"].items(), key=lambda item: item[1])
        if worst > gates["max_meta_ms"]:
            reasons.append(
                f"metadata {phase} {worst:.2f} ms/op above --max-meta-ms {gates['max_meta_ms']:.2f}"
            )
    if not gated:
        return "REPORT", []
    return ("FAIL" if reasons else "PASS"), reasons


def render(metrics, status, reasons):
    """Render the plain-text probe report."""
    meta = metrics["meta_ms"]
    lines = [
        f"io-probe: {metrics['dir']}  ({metrics['size_mb']:.0f} MiB file, "
        f"{metrics['meta_files']} metadata files)",
        f"  write     : {metrics['write_mbs']:8.1f} MiB/s (fsync included)",
        f"  read      : {metrics['read_mbs']:8.1f} MiB/s"
        + (
            "  (page-cache-assisted; the pages did not leave memory)"
            if metrics["read_cached"]
            else ""
        ),
        f"  metadata  : create {meta['create']:.2f}  stat {meta['stat']:.2f}  "
        f"delete {meta['delete']:.2f} ms/op",
    ]
    suffix = "" if not reasons else " (" + "; ".join(reasons) + ")"
    lines.append(f"verdict: {status}{suffix}")
    return "\n".join(lines)


def render_json(metrics, gates, status, reasons):
    """Render the structured probe result as JSON."""
    return json.dumps(dict(metrics, gates=gates, status=status, reasons=reasons), indent=2)


def _free_mib(directory):
    """Return the free space at a path in MiB, or None when it cannot be read."""
    try:
        stat = os.statvfs(directory)
    except OSError:
        return None
    return stat.f_bavail * stat.f_frsize / _MIB


def run_probe(directory, size_mb, meta_files, keep=False):
    """Probe directory and return the metrics dict.

    Creates a scratch subdirectory, measures write, read, and metadata, and
    removes the scratch directory unless keep. Raises ProbeError on setup or IO
    failure.
    """
    if not os.path.exists(directory):
        raise ProbeError(f"target directory does not exist: {directory}")
    if not os.path.isdir(directory):
        raise ProbeError(f"not a directory: {directory}")
    if is_memory_filesystem(directory):
        raise ProbeError(
            f"{directory} is tmpfs or ramfs, which is memory rather than storage. "
            "A probe there measures the memory subsystem and its read figure would "
            "be page cache whatever the report said"
        )
    free_mb = _free_mib(directory)
    if free_mb is not None and free_mb < size_mb:
        raise ProbeError(
            f"{directory} has {free_mb:.0f} MiB free, less than the {size_mb:.0f} MiB "
            "this probe would write"
        )
    host = socket.gethostname().split(".")[0]
    scratch = os.path.join(directory, f".io_probe.{host}.{os.getpid()}")
    try:
        os.mkdir(scratch)
    except OSError as exc:
        raise ProbeError(f"cannot create scratch dir: {exc}") from exc
    try:
        data_path = os.path.join(scratch, "data.bin")
        try:
            write_mbs, written_mb = measure_write(data_path, size_mb)
            read_mbs, read_cached = measure_read(data_path)
            meta_ms = measure_meta(scratch, meta_files)
        except OSError as exc:
            raise ProbeError(f"io failure during probe: {exc}") from exc
        return {
            "dir": directory,
            "size_mb": written_mb,
            "meta_files": meta_files,
            "write_mbs": write_mbs,
            "read_mbs": read_mbs,
            "read_cached": read_cached,
            "meta_ms": meta_ms,
        }
    finally:
        if not keep:
            shutil.rmtree(scratch, ignore_errors=True)
