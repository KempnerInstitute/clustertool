"""Filesystem responsiveness probe used by diag io-probe.

Not a benchmark: a seconds-long probe against a target directory that measures
bounded sequential write (fsync included) and read (page-cache assisted)
throughput plus small-file create/stat/delete latency.
"""

import json
import os
import shutil
import time

CHUNK = 4 * 1024 * 1024


class ProbeError(RuntimeError):
    """Raised when the probe cannot set up or complete its IO."""


def measure_write(path, size_mb):
    """Write about size_mb in whole CHUNK pieces with fsync; return (mb_per_s, mb_written)."""
    chunk = b"\0" * CHUNK
    chunks = max(1, int(size_mb * 1024 * 1024) // CHUNK)
    start = time.monotonic()
    with open(path, "wb") as handle:
        for _ in range(chunks):
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    elapsed = time.monotonic() - start
    total_mb = chunks * CHUNK / (1024.0 * 1024.0)
    return (total_mb / elapsed if elapsed > 0 else float("inf")), total_mb


def measure_read(path):
    """Re-read the file in CHUNK pieces; return mb_per_s (page-cache assisted)."""
    size_mb = os.path.getsize(path) / (1024.0 * 1024.0)
    start = time.monotonic()
    with open(path, "rb") as handle:
        while handle.read(CHUNK):
            pass
    elapsed = time.monotonic() - start
    return size_mb / elapsed if elapsed > 0 else float("inf")


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
                f"write {metrics['write_mbs']:.1f} MB/s below --min-write {gates['min_write']:.1f}"
            )
    if gates.get("min_read") is not None:
        gated = True
        if metrics["read_mbs"] < gates["min_read"]:
            reasons.append(
                f"read {metrics['read_mbs']:.1f} MB/s below --min-read {gates['min_read']:.1f}"
            )
    if gates.get("max_meta_ms") is not None:
        gated = True
        worst = max(metrics["meta_ms"].values())
        if worst > gates["max_meta_ms"]:
            reasons.append(
                f"metadata {worst:.2f} ms/op above --max-meta-ms {gates['max_meta_ms']:.2f}"
            )
    if not gated:
        return "REPORT", []
    return ("FAIL" if reasons else "PASS"), reasons


def render(metrics, status, reasons):
    """Render the plain-text probe report."""
    meta = metrics["meta_ms"]
    lines = [
        f"io-probe: {metrics['dir']}  ({metrics['size_mb']:.0f} MB file, "
        f"{metrics['meta_files']} metadata files)",
        f"  write     : {metrics['write_mbs']:8.1f} MB/s (fsync included)",
        f"  read      : {metrics['read_mbs']:8.1f} MB/s (page-cache-assisted on this host)",
        f"  metadata  : create {meta['create']:.2f}  stat {meta['stat']:.2f}  "
        f"delete {meta['delete']:.2f} ms/op",
    ]
    suffix = "" if not reasons else " (" + "; ".join(reasons) + ")"
    lines.append(f"verdict: {status}{suffix}")
    return "\n".join(lines)


def render_json(metrics, gates, status, reasons):
    """Render the structured probe result as JSON."""
    return json.dumps(dict(metrics, gates=gates, status=status, reasons=reasons), indent=2)


def run_probe(directory, size_mb, meta_files, keep=False):
    """Probe directory and return the metrics dict.

    Creates a scratch subdirectory, measures write, read, and metadata, and
    removes the scratch directory unless keep. Raises ProbeError on setup or IO
    failure.
    """
    if not os.path.isdir(directory):
        raise ProbeError(f"target directory does not exist: {directory}")
    scratch = os.path.join(directory, f".io_probe.{os.getpid()}")
    try:
        os.mkdir(scratch)
    except OSError as exc:
        raise ProbeError(f"cannot create scratch dir: {exc}") from exc
    try:
        data_path = os.path.join(scratch, "data.bin")
        try:
            write_mbs, written_mb = measure_write(data_path, size_mb)
            read_mbs = measure_read(data_path)
            meta_ms = measure_meta(scratch, meta_files)
        except OSError as exc:
            raise ProbeError(f"io failure during probe: {exc}") from exc
        return {
            "dir": directory,
            "size_mb": written_mb,
            "meta_files": meta_files,
            "write_mbs": write_mbs,
            "read_mbs": read_mbs,
            "read_cached": True,
            "meta_ms": meta_ms,
        }
    finally:
        if not keep:
            shutil.rmtree(scratch, ignore_errors=True)
