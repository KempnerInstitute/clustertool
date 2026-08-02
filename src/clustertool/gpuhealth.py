"""Node-local GPU hardware health from nvidia-smi.

Parses `nvidia-smi -q -x` (and `nvidia-smi nvlink -e`) and renders a tiered
OK/WARN/FAIL verdict per GPU and for the node, covering ECC and row-remap
state, clock throttling, and PCIe/NVLink error counters. A GPU that reports
nothing at all is a WARN rather than an OK, so that a health cron can tell a
clean GPU from one nothing could be read from. Hardware health only; for
utilization and profiling see `jobs scope`.
"""

import json
import re
import socket
import xml.etree.ElementTree as ET
from datetime import datetime

from clustertool import process

CORRECTABLE_ECC_WARN = 100
"""Volatile correctable errors above which to warn.

Single-bit errors are corrected in hardware and do not corrupt data, so this is
a rate-of-change hint rather than a fault. The count is volatile, meaning since
the last driver load, so it is not comparable between two nodes of different
uptime.
"""

PCIE_REPLAY_WARN = 80
"""PCIe replays above which to warn.

A replay is an ordinary link-layer retry, so a nonzero counter is not a fault.
NVIDIA's own DCGM diagnostic defaults its PCIe plugin to this same number.
"""

TEMP_MARGIN_C = 5
"""Warn when a GPU is within this many degrees of its slowdown threshold."""

SMI_TIMEOUT_S = 60

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"
NA = "n/a"
EXIT_ERROR = 3

_SEVERITY = {NA: 0, OK: 0, WARN: 1, FAIL: 2}
_EXIT_FOR = {OK: 0, WARN: 1, FAIL: 4}


class ProbeError(RuntimeError):
    """Raised when the nvidia-smi probe itself cannot run."""


def _find_text(node, *paths):
    """Return the first meaningful text at any candidate path, else None.

    Multiple paths cover tag renames across driver versions. Empty text and
    the literal 'N/A' both count as absent.
    """
    if node is None:
        return None
    for path in paths:
        el = node.find(path)
        if el is not None and el.text:
            text = el.text.strip()
            if text and text != "N/A":
                return text
    return None


def _to_int(text):
    if text is None:
        return None
    match = re.match(r"-?\d+", text)
    return int(match.group()) if match else None


def _to_float(text):
    if text is None:
        return None
    match = re.match(r"-?\d+(\.\d+)?", text)
    return float(match.group()) if match else None


def _yesno(text):
    """Map 'Yes'/'No' to bool, and None or anything else to None."""
    if text is None:
        return None
    return text.strip().lower() == "yes"


def _throttle_flag(node, *paths):
    """Map 'Active'/'Not Active' to bool, and an absent reason to None."""
    text = _find_text(node, *paths)
    if text is None:
        return None
    return text.strip().lower() == "active"


def _ecc_count(section, kind):
    """Total ECC errors of a kind in a volatile or aggregate section.

    Handles both the sram_*/dram_* layout (A100/H100) and the older
    single_bit/double_bit layout. Returns None when the section is absent.
    """
    if section is None:
        return None
    sram = _to_int(_find_text(section, f"sram_{kind}"))
    if sram is None and kind == "uncorrectable":
        parity = _to_int(_find_text(section, "sram_uncorrectable_parity"))
        secded = _to_int(_find_text(section, "sram_uncorrectable_secded"))
        if parity is not None or secded is not None:
            sram = (parity or 0) + (secded or 0)
    dram = _to_int(_find_text(section, f"dram_{kind}"))
    if sram is not None or dram is not None:
        return (sram or 0) + (dram or 0)
    old = "single_bit" if kind == "correctable" else "double_bit"
    return _to_int(_find_text(section, f"{old}/total"))


def parse_smi_xml(xml_text):
    """Parse `nvidia-smi -q -x` output.

    Returns {'driver_version': str|None, 'gpus': [dict, ...]}. Raises ValueError
    when the XML does not parse or has no <gpu>. Missing individual fields
    become None rather than an error.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"nvidia-smi XML did not parse: {exc}") from exc
    gpu_nodes = root.findall("gpu")
    if not gpu_nodes:
        raise ValueError("no <gpu> elements in nvidia-smi XML")

    gpus = []
    for position, node in enumerate(gpu_nodes):
        ecc = node.find("ecc_errors")
        volatile = ecc.find("volatile") if ecc is not None else None
        aggregate = ecc.find("aggregate") if ecc is not None else None
        remap = node.find("remapped_rows")
        throttle_node = node.find("clocks_throttle_reasons")
        if throttle_node is None:
            throttle_node = node.find("clocks_event_reasons")
        throttle = None
        if throttle_node is not None:
            throttle = {
                "sw_power_cap": _throttle_flag(
                    throttle_node,
                    "clocks_throttle_reason_sw_power_cap",
                    "clocks_event_reason_sw_power_cap",
                ),
                "sw_thermal": _throttle_flag(
                    throttle_node,
                    "clocks_throttle_reason_sw_thermal_slowdown",
                    "clocks_event_reason_sw_thermal_slowdown",
                ),
                "hw_thermal": _throttle_flag(
                    throttle_node,
                    "clocks_throttle_reason_hw_thermal_slowdown",
                    "clocks_event_reason_hw_thermal_slowdown",
                ),
                "hw_slowdown": _throttle_flag(
                    throttle_node,
                    "clocks_throttle_reason_hw_slowdown",
                    "clocks_event_reason_hw_slowdown",
                ),
                "hw_power_brake": _throttle_flag(
                    throttle_node,
                    "clocks_throttle_reason_hw_power_brake_slowdown",
                    "clocks_event_reason_hw_power_brake_slowdown",
                ),
            }
            if all(v is None for v in throttle.values()):
                throttle = None
        ecc_mode = _find_text(node, "ecc_mode/current_ecc")
        gpus.append(
            {
                "index": position,
                "minor_number": _to_int(_find_text(node, "minor_number")),
                "name": _find_text(node, "product_name"),
                "serial": _find_text(node, "serial"),
                "ecc_enabled": None if ecc_mode is None else ecc_mode.lower() == "enabled",
                "volatile_correctable": _ecc_count(volatile, "correctable"),
                "volatile_uncorrectable": _ecc_count(volatile, "uncorrectable"),
                "aggregate_uncorrectable": _ecc_count(aggregate, "uncorrectable"),
                "row_remap_pending": _yesno(_find_text(remap, "remapped_row_pending")),
                "row_remap_failure": _yesno(_find_text(remap, "remapped_row_failure")),
                "retired_pages_pending": _yesno(
                    _find_text(
                        node,
                        "retired_pages/pending_retirement",
                        "retired_pages/pending_blacklist",
                    )
                ),
                "sram_threshold_exceeded": _yesno(
                    _find_text(ecc, "aggregate/sram_threshold_exceeded")
                ),
                "throttle": throttle,
                "temp_c": _to_int(_find_text(node, "temperature/gpu_temp")),
                "slowdown_temp_c": _to_int(_find_text(node, "temperature/gpu_temp_slow_threshold")),
                "temp_margin_c": _to_int(_find_text(node, "temperature/gpu_temp_tlimit")),
                "power_w": _to_float(
                    _find_text(
                        node,
                        "gpu_power_readings/power_draw",
                        "gpu_power_readings/instant_power_draw",
                        "gpu_power_readings/average_power_draw",
                        "power_readings/power_draw",
                    )
                ),
                "power_limit_w": _to_float(
                    _find_text(
                        node,
                        "gpu_power_readings/current_power_limit",
                        "power_readings/current_power_limit",
                        "power_readings/power_limit",
                    )
                ),
                "pcie_replay": _to_int(_find_text(node, "pci/replay_counter")),
            }
        )
    return {"driver_version": _find_text(root, "driver_version"), "gpus": gpus}


_NVLINK_GPU_RE = re.compile(r"^GPU (\d+):")
_NVLINK_ERR_RE = re.compile(r"Link \d+:\s*([A-Za-z ]+?):\s*(\d+)\s*$")


def parse_nvlink(text):
    """Parse `nvidia-smi nvlink -e` output.

    Returns {gpu_index: {counter: total-across-links}}, and {} when the output
    has no per-GPU sections (no NVLink or unsupported), which callers treat as
    n/a.
    """
    per_gpu = {}
    current = None
    for line in (text or "").splitlines():
        header = _NVLINK_GPU_RE.match(line.strip())
        if header:
            current = int(header.group(1))
            per_gpu.setdefault(current, {})
            continue
        err = _NVLINK_ERR_RE.search(line)
        if err and current is not None:
            key = err.group(1).strip().lower().replace(" ", "_")
            per_gpu[current][key] = per_gpu[current].get(key, 0) + int(err.group(2))
    return per_gpu


def worst(tiers):
    """Return the worst tier in an iterable. NA never worsens; OK if empty."""
    result = OK
    for tier in tiers:
        if _SEVERITY.get(tier, 0) > _SEVERITY[result]:
            result = tier
    return result


_NORMAL_THROTTLE = frozenset({"sw_power_cap"})
"""Reasons that are ordinary clock management rather than a fault.

Per man nvidia-smi the SW power cap is the scaling algorithm holding a GPU at
its configured power limit, which is the steady state of a busy datacenter GPU.
"""


def evaluate(gpu, nvlink):
    """Return {check: (tier, detail)} for one GPU, per the verdict rules.

    `nvlink` is this GPU's counter dict from parse_nvlink, or None when NVLink
    data is unavailable.
    """
    checks = {}

    ecc_fields = (
        "volatile_uncorrectable",
        "aggregate_uncorrectable",
        "volatile_correctable",
        "row_remap_pending",
        "row_remap_failure",
        "retired_pages_pending",
        "sram_threshold_exceeded",
    )
    if gpu.get("ecc_enabled") is False:
        checks["ecc"] = (NA, "ECC disabled")
    elif all(gpu.get(f) is None for f in ecc_fields):
        checks["ecc"] = (NA, "not reported")
    elif gpu.get("volatile_uncorrectable"):
        count = gpu["volatile_uncorrectable"]
        checks["ecc"] = (FAIL, f"volatile uncorrectable ECC errors: {count}")
    elif gpu.get("sram_threshold_exceeded"):
        checks["ecc"] = (FAIL, "SRAM uncorrectable error threshold exceeded (RMA candidate)")
    elif gpu.get("row_remap_failure"):
        checks["ecc"] = (FAIL, "row remap failure (RMA candidate)")
    elif gpu.get("row_remap_pending"):
        checks["ecc"] = (FAIL, "row remap pending (GPU reset required)")
    elif gpu.get("retired_pages_pending"):
        checks["ecc"] = (FAIL, "retired pages pending (GPU reset required)")
    elif gpu.get("aggregate_uncorrectable"):
        count = gpu["aggregate_uncorrectable"]
        checks["ecc"] = (WARN, f"lifetime uncorrectable ECC errors: {count}")
    elif (gpu.get("volatile_correctable") or 0) > CORRECTABLE_ECC_WARN:
        count = gpu["volatile_correctable"]
        checks["ecc"] = (
            WARN,
            f"volatile correctable ECC errors: {count} (> {CORRECTABLE_ECC_WARN})",
        )
    else:
        counter_fields = (
            "volatile_uncorrectable",
            "aggregate_uncorrectable",
            "volatile_correctable",
        )
        if all(gpu.get(f) is None for f in counter_fields):
            checks["ecc"] = (OK, "(ECC counters not reported)")
        else:
            checks["ecc"] = (OK, "")

    throttle = gpu.get("throttle")
    temp, slowdown = gpu.get("temp_c"), gpu.get("slowdown_temp_c")
    margin = gpu.get("temp_margin_c")
    active = sorted(k for k, v in (throttle or {}).items() if v)
    hardware = sorted({"hw_slowdown", "hw_power_brake"} & set(active))
    concerning = sorted(set(active) - _NORMAL_THROTTLE - set(hardware))
    hot = temp is not None and slowdown is not None and temp >= slowdown - TEMP_MARGIN_C
    reported = throttle is not None and any(v is not None for v in throttle.values())
    if not reported and temp is None and margin is None:
        checks["throttle"] = (NA, "not reported")
    elif hardware:
        checks["throttle"] = (FAIL, f"hardware slowdown active: {', '.join(hardware)}")
    elif concerning:
        checks["throttle"] = (WARN, f"throttling active: {', '.join(concerning)}")
    elif hot:
        detail = f"temperature {temp}C within {TEMP_MARGIN_C}C of slowdown threshold {slowdown}C"
        checks["throttle"] = (WARN, detail)
    elif slowdown is None and margin is not None and margin <= TEMP_MARGIN_C:
        checks["throttle"] = (WARN, f"{margin}C of thermal margin left (warn at {TEMP_MARGIN_C}C)")
    elif active:
        checks["throttle"] = (OK, f"at the power cap, which is normal: {', '.join(active)}")
    else:
        checks["throttle"] = (OK, "")

    replay = gpu.get("pcie_replay")
    if replay is None:
        checks["pcie"] = (NA, "not reported")
    elif replay > PCIE_REPLAY_WARN:
        checks["pcie"] = (WARN, f"PCIe replay counter: {replay} (> {PCIE_REPLAY_WARN})")
    else:
        checks["pcie"] = (OK, "")

    if nvlink is None:
        checks["nvlink"] = (NA, "no NVLink data")
    else:
        nonzero = {k: v for k, v in nvlink.items() if v}
        if nonzero:
            detail = ", ".join(f"{k}={v}" for k, v in sorted(nonzero.items()))
            checks["nvlink"] = (WARN, f"NVLink errors: {detail}")
        else:
            checks["nvlink"] = (OK, "")

    return checks


def _row_remap_state(gpu):
    if gpu["row_remap_failure"] is None and gpu["row_remap_pending"] is None:
        return NA
    if gpu["row_remap_failure"]:
        return "failure"
    if gpu["row_remap_pending"]:
        return "pending"
    return "none"


def build_result(parsed, nvlink_by_gpu, host=None, timestamp=None):
    """Assemble the snapshot dict (the --json schema).

    nvlink_by_gpu is parse_nvlink() output, or None when NVLink data is entirely
    unavailable. An empty per-GPU dict is treated as n/a, not a clean OK. host
    and timestamp are injectable for tests.
    """
    gpus_out = []
    for gpu in parsed["gpus"]:
        nvlink = None
        if nvlink_by_gpu is not None:
            nvlink = nvlink_by_gpu.get(gpu["index"]) or None
        checks = evaluate(gpu, nvlink)
        blind = all(tier == NA for tier, _ in checks.values())
        gpus_out.append(
            {
                "index": gpu["index"],
                "minor_number": gpu["minor_number"],
                "name": gpu["name"],
                "serial": gpu["serial"],
                "verdict": WARN if blind else worst(tier for tier, _ in checks.values()),
                "verdict_detail": "nothing could be read from this GPU" if blind else "",
                "checks": {
                    "ecc": {
                        "status": checks["ecc"][0],
                        "detail": checks["ecc"][1],
                        "volatile_uncorrectable": gpu["volatile_uncorrectable"],
                        "aggregate_uncorrectable": gpu["aggregate_uncorrectable"],
                        "volatile_correctable": gpu["volatile_correctable"],
                        "row_remap": _row_remap_state(gpu),
                        "sram_threshold_exceeded": gpu["sram_threshold_exceeded"],
                    },
                    "throttle": {
                        "status": checks["throttle"][0],
                        "detail": checks["throttle"][1],
                        "active": sorted(k for k, v in (gpu["throttle"] or {}).items() if v),
                        "temp_c": gpu["temp_c"],
                        "slowdown_temp_c": gpu["slowdown_temp_c"],
                        "temp_margin_c": gpu["temp_margin_c"],
                        "power_w": gpu["power_w"],
                        "power_limit_w": gpu["power_limit_w"],
                    },
                    "pcie": {
                        "status": checks["pcie"][0],
                        "detail": checks["pcie"][1],
                        "replay_counter": gpu["pcie_replay"],
                    },
                    "nvlink": {
                        "status": checks["nvlink"][0],
                        "detail": checks["nvlink"][1],
                        "errors": {k: v for k, v in (nvlink or {}).items() if v},
                    },
                },
            }
        )
    return {
        "host": host or socket.gethostname().split(".")[0],
        "timestamp": timestamp or datetime.now().isoformat(timespec="seconds"),
        "driver_version": parsed["driver_version"],
        "verdict": worst(g["verdict"] for g in gpus_out),
        "gpus": gpus_out,
    }


def render_text(result):
    """Render the plain-text report: header, one block per GPU, node verdict."""
    driver = result["driver_version"] or NA
    lines = [f"gpu-health @ {result['host']}  (driver {driver}, {result['timestamp']})", ""]
    for gpu in result["gpus"]:
        name = gpu["name"] or "?"
        serial = gpu["serial"] or NA
        minor = gpu["minor_number"]
        device = f", /dev/nvidia{minor}" if minor is not None else ""
        lines.append(f"GPU {gpu['index']}: {name}  (serial {serial}{device})")
        for check_name in ("ecc", "throttle", "pcie", "nvlink"):
            check = gpu["checks"][check_name]
            line = f"  {check_name + ':':<9} {check['status']}"
            if check["detail"]:
                line += " - " + check["detail"]
            lines.append(line)
        note = gpu.get("verdict_detail")
        lines.append(f"  verdict:  {gpu['verdict']}" + (f" - {note}" if note else ""))
        lines.append("")
    verdict = result["verdict"]
    suffix = ""
    if verdict != OK:
        culprits = [str(g["index"]) for g in result["gpus"] if g["verdict"] == verdict]
        suffix = f" (GPU {', GPU '.join(culprits)})"
    lines.append(f"node verdict: {verdict}{suffix}")
    return "\n".join(lines)


def render_json(result):
    return json.dumps(result, indent=2) + "\n"


def exit_code(verdict):
    """Return the process exit status for a node verdict.

    0 OK, 1 WARN, 4 FAIL. 2 is skipped throughout the diagnostics because click
    exits 2 on a usage error, which a caller must be able to tell from a fault
    the probe actually found.
    """
    return _EXIT_FOR[verdict]


def collect():
    """Run nvidia-smi and return (xml_text, nvlink_text_or_None).

    Raises ProbeError when the probe itself cannot run, including a wedged
    nvidia-smi that exceeds the timeout. A failing or timed-out
    `nvidia-smi nvlink` only degrades NVLink data to n/a.
    """
    code, stdout, stderr = process.probe(["nvidia-smi", "-q", "-x"], timeout=SMI_TIMEOUT_S)
    if code == 127:
        raise ProbeError("nvidia-smi not found on this host")
    if code == 124:
        raise ProbeError("nvidia-smi -q -x timed out")
    if code != 0:
        raise ProbeError(f"nvidia-smi -q -x failed: {stderr.strip() or f'exit {code}'}")
    nvl_code, nvl_out, _ = process.probe(["nvidia-smi", "nvlink", "-e"], timeout=SMI_TIMEOUT_S)
    return stdout, (nvl_out if nvl_code == 0 else None)
