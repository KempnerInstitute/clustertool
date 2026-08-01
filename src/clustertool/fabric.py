"""InfiniBand fabric diagnostics helpers for the diag ib-* commands."""

import datetime
import os
import re
from pathlib import Path

from clustertool import process

_GPU_QUERY = (
    "index,name,pci.bus_id,temperature.gpu,power.draw,power.limit,"
    "memory.total,memory.used,clocks.current.sm,clocks.current.memory"
)

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


_TOPO_ROW_RE = re.compile(r"^(GPU|NIC|mlx)\S*", re.IGNORECASE)


def _gpu_identity(snapshot: dict) -> list:
    return [
        (gpu.get("index"), gpu.get("name"), gpu.get("pci_bus_id"))
        for gpu in (snapshot.get("gpus") or [])
    ]


def _hca_port_identity(snapshot: dict) -> dict:
    out = {}
    for hca in (snapshot.get("ib") or {}).get("hcas") or []:
        for port in hca.get("ports") or []:
            key = f"{hca.get('name')}/port{port.get('port')}"
            out[key] = {f: port.get(f) for f in ("state", "phys_state", "rate", "link_layer")}
    return out


def _netdev_mapping(snapshot: dict) -> list:
    return sorted(
        (m.get("hca"), m.get("port"), m.get("netdev")) for m in (snapshot.get("ibdev2netdev") or [])
    )


def _topo_rows(snapshot: dict) -> list:
    raw = (snapshot.get("topology") or {}).get("raw") or ""
    return [
        " ".join(line.split())
        for line in raw.splitlines()
        if line.strip() and _TOPO_ROW_RE.match(line.strip())
    ]


def _info_fields(snapshot: dict) -> dict:
    system = snapshot.get("system") or {}
    uname = (system.get("uname") or "").split()
    return {
        "driver": system.get("nvidia_driver"),
        "kernel": uname[2] if len(uname) > 2 else None,
        "cuda": system.get("cuda_runtime"),
    }


def compare_snapshots(golden: dict, current: dict) -> dict:
    """Identity-field diff of two snapshots: {'hardware': [...], 'informational': [...]}.

    Hardware drift covers GPU inventory, HCA port state/rate/link, the netdev
    mapping, and the topology matrix. Driver, kernel, and CUDA changes are
    informational.
    """
    hardware: list[str] = []
    informational: list[str] = []

    current_hcas = (current.get("ib") or {}).get("hcas")
    if (golden.get("ib") or {}).get("hcas") and not current_hcas:
        hardware.append("ib section unavailable in current snapshot")

    gpu_g, gpu_c = _gpu_identity(golden), _gpu_identity(current)
    if gpu_g != gpu_c:
        hardware.append(f"gpu inventory: golden={gpu_g} current={gpu_c}")

    g_ports, c_ports = _hca_port_identity(golden), _hca_port_identity(current)
    for key in sorted(set(g_ports) | set(c_ports)):
        if key not in c_ports:
            if current_hcas:
                hardware.append(f"{key}: missing in current snapshot")
            continue
        if key not in g_ports:
            hardware.append(f"{key}: not present in golden snapshot")
            continue
        for field in ("state", "phys_state", "rate", "link_layer"):
            if g_ports[key][field] != c_ports[key][field]:
                gv, cv = g_ports[key][field], c_ports[key][field]
                hardware.append(f"{key} {field}: golden={gv} current={cv}")

    map_g, map_c = _netdev_mapping(golden), _netdev_mapping(current)
    if map_g != map_c:
        hardware.append(f"ibdev2netdev mapping: golden={map_g} current={map_c}")

    if _topo_rows(golden) != _topo_rows(current):
        hardware.append("topology matrix rows changed")

    info_g, info_c = _info_fields(golden), _info_fields(current)
    for field in sorted(info_g):
        if info_g[field] != info_c[field]:
            informational.append(f"{field}: golden={info_g[field]} current={info_c[field]}")

    return {"hardware": hardware, "informational": informational}


def render_drift(findings: dict, strict: bool) -> str:
    """Render drift findings as text with a MATCH or DRIFT verdict."""
    lines = []
    if findings["hardware"]:
        lines.append(f"Hardware drift ({len(findings['hardware'])}):")
        lines.extend("  " + item for item in findings["hardware"])
    if findings["informational"]:
        suffix = "" if strict else " (not counted without --strict)"
        lines.append(f"Informational drift ({len(findings['informational'])}){suffix}:")
        lines.extend("  " + item for item in findings["informational"])
    drift = findings["hardware"] or (strict and findings["informational"])
    lines.append(f"verdict: {'DRIFT' if drift else 'MATCH'}")
    return "\n".join(lines)


_ERROR_COUNTERS = frozenset(
    {
        "symbol_error",
        "link_downed",
        "link_error_recovery",
        "port_rcv_errors",
        "port_rcv_remote_physical_errors",
        "port_rcv_switch_relay_errors",
        "port_xmit_discards",
        "port_xmit_constraint_errors",
        "port_rcv_constraint_errors",
        "local_link_integrity_errors",
        "excessive_buffer_overrun_errors",
        "VL15_dropped",
        "port_xmit_wait",
    }
)


def counters_by_port(snapshot: dict) -> dict[str, dict]:
    """Return {hca/portN: counters} from an ib-snapshot, InfiniBand ports only.

    An adapter in Ethernet mode exposes the same counter files, and on many hosts
    they read back as errors. They are not InfiniBand counters, so including them
    would judge the fabric on ports that are not part of it.
    """
    result = {}
    for hca in snapshot.get("ib", {}).get("hcas", []):
        for port in hca.get("ports", []):
            link_layer = port.get("link_layer")
            if link_layer is not None and link_layer != "InfiniBand":
                continue
            result[f"{hca['name']}/port{port['port']}"] = port.get("counters") or {}
    return result


def counter_deltas(before: dict, after: dict) -> tuple[list[tuple], bool]:
    """Diff two snapshots' per-port counters.

    Returns (rows, any_error) where rows is
    (port, counter, before, after, delta, is_error) for every counter worth
    reporting, and any_error is True when an error-class counter advanced.

    A counter unreadable on both sides is skipped: that is a property of the port,
    not a change. One readable and one not is reported with a delta of None rather
    than treated as zero, which would turn an unreadable baseline into a
    full-magnitude error. An error counter that went backwards was reset
    between the snapshots, so its whole after value is new and unaccounted for;
    that counts as an error rather than as no growth.
    """
    a = counters_by_port(before)
    b = counters_by_port(after)
    rows = []
    any_error = False
    for port in sorted(set(a) | set(b)):
        a_counters, b_counters = a.get(port, {}), b.get(port, {})
        for counter in sorted(set(a_counters) | set(b_counters)):
            before_v = a_counters.get(counter)
            after_v = b_counters.get(counter)
            is_error_counter = counter in _ERROR_COUNTERS
            if before_v is None and after_v is None:
                continue
            if before_v is None or after_v is None:
                rows.append((port, counter, before_v, after_v, None, is_error_counter))
                any_error = any_error or is_error_counter
                continue
            delta = after_v - before_v
            if delta == 0:
                continue
            is_error = is_error_counter and delta != 0
            rows.append((port, counter, before_v, after_v, delta, is_error))
            any_error = any_error or is_error
    return rows, any_error


def collect_snapshot(ib_root: str = "/sys/class/infiniband", timestamp: str | None = None) -> dict:
    """Probe the node and return the IB/GPU snapshot dict (the ib-snapshot schema).

    A probe that could not run records why under probe_errors, so an empty field
    means the node really has nothing to report rather than that the tool was
    missing or timed out.
    """
    errors: dict[str, str] = {}

    def out(cmd):
        code, stdout, _ = process.probe(cmd, timeout=30)
        if code == 127:
            errors[cmd[0]] = "not installed"
        elif code == 124:
            errors[" ".join(cmd)] = "timed out after 30s"
        elif code:
            errors[" ".join(cmd)] = f"exited {code}"
        return stdout

    driver = out(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader,nounits"])
    driver_lines = driver.splitlines()
    stamp = timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    snapshot = {
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
    snapshot["probe_errors"] = errors
    return snapshot
