"""Live per-node GPU/CPU/memory/InfiniBand monitor."""

import concurrent.futures
import importlib.resources
import sys
import time

from clustertool.process import CommandError, probe

_SSH_OPTS = [
    "-o",
    "ConnectTimeout=3",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "BatchMode=yes",
]

_SSH_TIMEOUT_S = 20
"""Cap on one sample, since ConnectTimeout does not bound a session that stalls.

man ssh_config says ConnectTimeout applies only while connecting, so a host that
completes the handshake and then hangs in the login path would otherwise block
the whole table indefinitely.
"""

_SSH_NOISE = ("Warning: Permanently added", "Permanently added")

# Fractions of a modern IB link: below _IB_LOW_MBS a fabric is effectively idle.
_IB_LOW_MBS = 500.0
_IB_HIGH_MBS = 2000.0
_GREEN, _YELLOW, _RED, _RESET = "\033[32m", "\033[33m", "\033[31m", "\033[0m"

_SAMPLE_SCRIPT = (
    importlib.resources.files("clustertool") / "data" / "monitor_sample.sh"
).read_text()


def ssh_reason(err: str) -> str:
    """Return the first line of ssh stderr that says why a host was not reached."""
    for line in err.splitlines():
        line = line.strip()
        if line and not line.startswith(_SSH_NOISE):
            return line
    return "ssh failed"


def num_gpus(host: str) -> int:
    """Return the number of GPUs on a host, or 0 if it cannot be detected."""
    _, out, _ = probe(
        [
            "ssh",
            *_SSH_OPTS,
            host,
            "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader | wc -l",
        ],
        timeout=_SSH_TIMEOUT_S,
    )
    try:
        return int(out.strip())
    except ValueError:
        return 0


def sample(host: str) -> tuple[str, str]:
    """Return (raw stats line, failure reason) from a host.

    The reason is empty when the host answered. It is carried alongside the line
    rather than discarded, so a row of N/A can say whether the node reported
    nothing or refused the login.
    """
    code, out, err = probe(
        ["ssh", *_SSH_OPTS, host, "bash"], timeout=_SSH_TIMEOUT_S, input_text=_SAMPLE_SCRIPT
    )
    if code == 124:
        return "", f"no answer within {_SSH_TIMEOUT_S}s"
    if code:
        return "", ssh_reason(err)
    return out, ""


def parse_sample(raw: str):
    """Parse a raw stats line into (gpus, cpu, mem, net) or None.

    The sampler closes the line with its InfiniBand port count, so a node with
    more or fewer HCAs than another is read correctly rather than truncated.
    """
    fields = raw.split()
    if not fields or not fields[-1].isdigit():
        return None
    count = int(fields[-1])
    fields = fields[:-1]
    if len(fields) < 2 + count:
        return None
    net = fields[len(fields) - count :] if count else []
    mem = fields[-count - 1]
    cpu = fields[-count - 2]
    gpu_fields = fields[: len(fields) - count - 2]
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


def _header(title: str, gpus: int, ports: int, interval: int) -> str:
    width = 20 + gpus * 20 + 12 + 13 + ports * 14
    lines = [
        title,
        f"Updated every {interval} seconds. Press Ctrl+C to quit.",
        "-" * width,
    ]
    cols = _pad("Hostname", "Hostname", 20)
    for i in range(gpus):
        cols += _pad(f"GPU{i}(C/M)", f"GPU{i}(C/M)", 20)
    cols += _pad("CPU(%)", "CPU(%)", 12) + _pad("Mem(%)", "Mem(%)", 13)
    for i in range(ports):
        cols += _pad(f"ib{i}(MB/s)", f"ib{i}(MB/s)", 14)
    lines.append(cols)
    lines.append("-" * width)
    return "\n".join(lines)


def _row(host: str, raw: str, gpus: int, ports: int) -> str:
    row = _pad(host, host, 20)
    parsed = parse_sample(raw)
    if parsed is None:
        for _ in range(gpus):
            row += _pad("N/A/N/A", "N/A/N/A", 20)
        row += _pad("N/A", "N/A", 12) + _pad("N/A", "N/A", 13)
        for _ in range(ports):
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
    for i in range(ports):
        row += _cell(
            net[i] if i < len(net) else "N/A", _IB_LOW_MBS, _IB_HIGH_MBS, 14, idle_is_bad=True
        )
    return row


def _port_count(samples: list[str]) -> int:
    """Return the widest InfiniBand port count across the sampled hosts.

    The table is drawn once and then redrawn in place, so the column count is
    fixed for the run and has to hold the busiest node.
    """
    parsed = [parse_sample(raw) for raw, _ in samples]
    return max((len(row[3]) for row in parsed if row), default=0)


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

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(hosts), 32)) as pool:
        samples = list(pool.map(sample, hosts))
    ports = _port_count(samples)

    print(_header(title, gpus, ports, interval))
    for _ in hosts:
        print()
    reported: set[str] = set()
    try:
        while True:
            sys.stdout.write(f"\033[{len(hosts)}A")
            for host, (raw, _) in zip(hosts, samples, strict=True):
                sys.stdout.write("\033[2K")
                print(_row(host, raw, gpus, ports))
            sys.stdout.flush()
            for host, (_, reason) in zip(hosts, samples, strict=True):
                if reason and (host, reason) not in reported:
                    reported.add((host, reason))
                    print(f"  {host}: {reason}", file=sys.stderr)
            time.sleep(interval)
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(hosts), 32)) as pool:
                samples = list(pool.map(sample, hosts))
    except KeyboardInterrupt:
        print()
