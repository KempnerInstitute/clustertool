"""Live per-node GPU/CPU/memory/InfiniBand monitor."""

import concurrent.futures
import importlib.resources
import sys
import time

from clustertool.process import CommandError, run

_SSH_OPTS = [
    "-o",
    "ConnectTimeout=3",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "LogLevel=ERROR",
]
_NUM_IB = 4

# Fractions of a modern IB link: below _IB_LOW_MBS a fabric is effectively idle.
_IB_LOW_MBS = 500.0
_IB_HIGH_MBS = 2000.0
_GREEN, _YELLOW, _RED, _RESET = "\033[32m", "\033[33m", "\033[31m", "\033[0m"

_SAMPLE_SCRIPT = (
    importlib.resources.files("clustertool") / "data" / "monitor_sample.sh"
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


def _colorize(
    value: str, low: float, high: float, unit: str = "", idle_is_bad: bool = False
) -> str:
    """Wrap a value in a green/yellow/red color by threshold.

    Set idle_is_bad for a metric that should be high, such as GPU utilization,
    which inverts the scale.
    """
    try:
        num = float(str(value).rstrip("%"))
    except ValueError:
        return f"{value}{unit}"
    if idle_is_bad:
        color = _RED if num < low else _YELLOW if num < high else _GREEN
    else:
        color = _RED if num > high else _YELLOW if num > low else _GREEN
    return f"{color}{value}{unit}{_RESET}"


def _pad(text: str, plain: str, width: int) -> str:
    return text + " " * max(width - len(plain), 0)


def _cell(
    value: str, low: float, high: float, width: int, unit: str = "", idle_is_bad: bool = False
) -> str:
    return _pad(_colorize(value, low, high, unit, idle_is_bad=idle_is_bad), f"{value}{unit}", width)


def _header(title: str, gpus: int, interval: int) -> str:
    width = 20 + gpus * 20 + 12 + 13 + _NUM_IB * 14
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
            cell = _colorize(gu, 50, 80, "%", idle_is_bad=True) + "/" + _colorize(mu, 60, 90, "%")
            row += _pad(cell, f"{gu}%/{mu}%", 20)
        else:
            row += _pad("N/A/N/A", "N/A/N/A", 20)
    row += _cell(cpu, 50, 80, 12) + _cell(mem, 70, 90, 13)
    for i in range(_NUM_IB):
        row += _cell(
            net[i] if i < len(net) else "N/A", _IB_LOW_MBS, _IB_HIGH_MBS, 14, idle_is_bad=True
        )
    return row


def run_monitor(title: str, hosts: list[str], interval: int) -> None:
    """Render a live refreshing table of per-node stats until interrupted."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(hosts), 32)) as pool:
        counts = list(pool.map(num_gpus, hosts))
    gpus = max(counts, default=0)
    if gpus < 1:
        raise CommandError(
            f"could not detect GPUs on any of the {len(hosts)} host(s). This needs "
            "passwordless ssh to them, and nvidia-smi there. Where node login "
            "requires an allocation on the node, monitor a job's own nodes instead"
        )

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
