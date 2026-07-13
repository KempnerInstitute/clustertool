"""Live per-node GPU/CPU/memory/InfiniBand monitor."""

import concurrent.futures
import importlib.resources
import sys
import time

from cluster_tools.process import CommandError, run

_SSH_OPTS = [
    "-o",
    "ConnectTimeout=3",
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "LogLevel=ERROR",
]
_NUM_IB = 4
_GREEN, _YELLOW, _RED, _RESET = "\033[32m", "\033[33m", "\033[31m", "\033[0m"

_SAMPLE_SCRIPT = (
    importlib.resources.files("cluster_tools") / "data" / "monitor_sample.sh"
).read_text()


def num_gpus(host: str) -> int:
    """Return the number of GPUs on a host, or 0 if it cannot be detected."""
    out = run(
        [
            "ssh",
            *_SSH_OPTS,
            host,
            "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader | wc -l",
        ]
    )
    try:
        return int(out.strip())
    except ValueError:
        return 0


def sample(host: str) -> str:
    """Return one raw stats line from a host."""
    return run(["ssh", *_SSH_OPTS, host, "bash"], input_text=_SAMPLE_SCRIPT)


def parse_sample(raw: str):
    """Parse a raw stats line into (gpus, cpu, mem, net) or None."""
    fields = raw.split()
    if len(fields) < 2 + _NUM_IB:
        return None
    net = fields[-_NUM_IB:]
    mem = fields[-_NUM_IB - 1]
    cpu = fields[-_NUM_IB - 2]
    gpu_fields = fields[: -_NUM_IB - 2]
    gpus = [(gpu_fields[i], gpu_fields[i + 1]) for i in range(0, len(gpu_fields) - 1, 2)]
    return gpus, cpu, mem, net


def _colorize(value: str, low: float, high: float, unit: str = "") -> str:
    """Wrap a value in a green/yellow/red color by threshold."""
    try:
        num = float(str(value).rstrip("%"))
    except ValueError:
        return f"{value}{unit}"
    color = _RED if num > high else _YELLOW if num > low else _GREEN
    return f"{color}{value}{unit}{_RESET}"


def _pad(text: str, plain: str, width: int) -> str:
    return text + " " * max(width - len(plain), 0)


def _cell(value: str, low: float, high: float, width: int, unit: str = "") -> str:
    return _pad(_colorize(value, low, high, unit), f"{value}{unit}", width)


def _header(title: str, gpus: int, interval: int) -> str:
    width = 20 + gpus * 21 + 12 + 13 + _NUM_IB * 14
    lines = [
        title,
        f"Updated every {interval} seconds. Press Ctrl+C to quit.",
        "-" * width,
    ]
    cols = _pad("Hostname", "Hostname", 20)
    for i in range(gpus):
        cols += _pad(f"GPU{i}(C/M)", f"GPU{i}(C/M)", 20)
    cols += _pad("CPU(%)", "CPU(%)", 12) + _pad("Mem(%)", "Mem(%)", 13)
    for i in range(_NUM_IB):
        cols += _pad(f"ib{i}(MB/s)", f"ib{i}(MB/s)", 14)
    lines.append(cols)
    lines.append("-" * width)
    return "\n".join(lines)


def _row(host: str, raw: str, gpus: int) -> str:
    row = _pad(host, host, 20)
    parsed = parse_sample(raw)
    if parsed is None:
        for _ in range(gpus):
            row += _pad("N/A/N/A", "N/A/N/A", 20)
        row += _pad("N/A", "N/A", 12) + _pad("N/A", "N/A", 13)
        for _ in range(_NUM_IB):
            row += _pad("N/A", "N/A", 14)
        return row
    gpu_cells, cpu, mem, net = parsed
    for i in range(gpus):
        if i < len(gpu_cells):
            gu, mu = gpu_cells[i]
            cell = _colorize(gu, 50, 80, "%") + "/" + _colorize(mu, 60, 90, "%")
            row += _pad(cell, f"{gu}%/{mu}%", 20)
        else:
            row += _pad("N/A/N/A", "N/A/N/A", 20)
    row += _cell(cpu, 50, 80, 12) + _cell(mem, 70, 90, 13)
    for i in range(_NUM_IB):
        row += _cell(net[i] if i < len(net) else "N/A", 10, 30, 14)
    return row


def run_monitor(title: str, hosts: list[str], interval: int) -> None:
    """Render a live refreshing table of per-node stats until interrupted."""
    gpus = num_gpus(hosts[0])
    if gpus < 1:
        raise CommandError(f"could not detect GPUs on {hosts[0]}")

    print(_header(title, gpus, interval))
    for _ in hosts:
        print()
    try:
        while True:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(hosts), 32)) as pool:
                samples = list(pool.map(sample, hosts))
            sys.stdout.write(f"\033[{len(hosts)}A")
            for host, raw in zip(hosts, samples, strict=True):
                sys.stdout.write("\033[2K")
                print(_row(host, raw, gpus))
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        print()
