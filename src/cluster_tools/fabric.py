"""InfiniBand fabric diagnostics helpers for the diag ib-* commands."""

import datetime
import os
import re
from pathlib import Path

from cluster_tools import process

_GPU_QUERY = (
    "index,name,pci.bus_id,temperature.gpu,power.draw,power.limit,"
    "memory.total,memory.used,clocks.current.sm,clocks.current.memory"
)

# nvidia-smi topo connection qualities, best to worst. A score below NODE means
# the GPU reaches its nearest NIC only across a NUMA boundary.
_QUALITY = {
    "NV18": 10,
    "NV12": 10,
    "NV8": 10,
    "NV6": 10,
    "NV4": 10,
    "NV2": 10,
    "NV1": 10,
    "NVL": 10,
    "PIX": 6,
    "PXB": 5,
    "PHB": 4,
    "NODE": 3,
    "SYS": 1,
    "X": 0,
}
AFFINITY_OK = 3  # NODE or better

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def quality_score(quality: str) -> int:
    """Return the closeness score for an nvidia-smi topo connection quality."""
    return _QUALITY.get(quality, 0)


def parse_topo(raw: str) -> dict[str, dict[str, str]]:
    """Parse `nvidia-smi topo -m` into {gpu: {nic: quality}}.

    The header row lists the GPU and NIC columns with no row-label cell, while
    each data row leads with its own label, so a row's value at index i belongs
    to header column i. Returns {} when there are no NIC columns or GPU rows.
    """
    lines = [_ANSI_RE.sub("", line).rstrip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return {}
    header = lines[0].split()
    nic_cols = [(i, name) for i, name in enumerate(header) if name.startswith("NIC")]
    if not nic_cols:
        return {}
    result: dict[str, dict[str, str]] = {}
    for line in lines[1:]:
        if not line.startswith("GPU"):
            continue
        parts = line.split()
        values = parts[1:]
        conn = {nic: (values[i].strip() if i < len(values) else "?") for i, nic in nic_cols}
        result[parts[0]] = conn
    return result


def affinity_rows(matrix: dict[str, dict[str, str]]) -> list[tuple[str, str, str, str]]:
    """Return (gpu, best_nic, best_quality, verdict) per GPU from a topo matrix.

    The verdict is OK for NODE or closer, WARN when the best link crosses a NUMA
    boundary, and FAIL when the GPU reaches no NIC.
    """
    rows = []
    for gpu, conns in matrix.items():
        best_nic, best_q = max(conns.items(), key=lambda item: quality_score(item[1]))
        score = quality_score(best_q)
        verdict = "OK" if score >= AFFINITY_OK else "WARN" if score > 0 else "FAIL"
        rows.append((gpu, best_nic, best_q, verdict))
    return rows


def _to_int(text):
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return None


def _to_float(text):
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _read_first(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def parse_gpu_csv(output: str) -> list[dict]:
    """Parse nvidia-smi --query-gpu CSV rows into GPU dicts."""
    rows = []
    for line in output.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 10:
            continue
        rows.append(
            {
                "index": _to_int(parts[0]),
                "name": parts[1],
                "pci_bus_id": parts[2],
                "temp_c": _to_float(parts[3]),
                "power_draw_w": _to_float(parts[4]),
                "power_limit_w": _to_float(parts[5]),
                "memory_total_mib": _to_int(parts[6]),
                "memory_used_mib": _to_int(parts[7]),
                "sm_clock_mhz": _to_int(parts[8]),
                "memory_clock_mhz": _to_int(parts[9]),
            }
        )
    return rows


def parse_ibdev2netdev(output: str) -> list[dict]:
    """Parse ibdev2netdev lines like 'mlx5_0 port 1 ==> ib0 (Up)'."""
    mapping = []
    for line in output.strip().splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == "==>":
            state = parts[5].strip("()") if len(parts) > 5 else None
            mapping.append(
                {"hca": parts[0], "port": _to_int(parts[2]), "netdev": parts[4], "state": state}
            )
    return mapping


def read_hcas(root: str = "/sys/class/infiniband") -> list[dict]:
    """Read IB HCA ports (state, rate, link_layer) and counters from sysfs."""
    base = Path(root)
    if not base.exists():
        return []
    hcas = []
    for hca_dir in sorted(base.iterdir()):
        ports = []
        ports_dir = hca_dir / "ports"
        if ports_dir.exists():
            for port_dir in sorted(ports_dir.iterdir()):
                port = {"port": _to_int(port_dir.name)}
                for key in ("state", "phys_state", "rate", "link_layer"):
                    port[key] = _read_first(port_dir / key)
                counters_dir = port_dir / "counters"
                if counters_dir.exists():
                    port["counters"] = {
                        c.name: _to_int(_read_first(c))
                        for c in sorted(counters_dir.iterdir())
                        if c.is_file()
                    }
                ports.append(port)
        hcas.append({"name": hca_dir.name, "ports": ports})
    return hcas


def collect_snapshot(ib_root: str = "/sys/class/infiniband", timestamp: str | None = None) -> dict:
    """Probe the node and return the IB/GPU snapshot dict (the ib-snapshot schema)."""

    def out(cmd):
        return process.probe(cmd, timeout=30)[1]

    driver = out(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader,nounits"])
    driver_lines = driver.splitlines()
    stamp = timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    return {
        "schema_version": 1,
        "timestamp_utc": stamp,
        "hostname": os.uname().nodename,
        "system": {
            "uname": out(["uname", "-a"]).strip(),
            "nvidia_driver": driver_lines[0].strip() if driver_lines else None,
        },
        "gpus": parse_gpu_csv(
            out(["nvidia-smi", f"--query-gpu={_GPU_QUERY}", "--format=csv,noheader,nounits"])
        ),
        "topology": {"raw": out(["nvidia-smi", "topo", "-m"])},
        "nvlink": {"raw": out(["nvidia-smi", "nvlink", "--status"])},
        "ib": {"hcas": read_hcas(ib_root)},
        "ibdev2netdev": parse_ibdev2netdev(out(["ibdev2netdev"])),
    }
