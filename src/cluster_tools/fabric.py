"""InfiniBand fabric diagnostics helpers for the diag ib-* commands."""

import re

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
